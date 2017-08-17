#!/usr/bin/env python2
# vim: set fileencoding=utf8

from __future__ import unicode_literals

import re
import asyncio
from bs4 import BeautifulSoup
import json

from mycoro import MyCoro
from config import forum_config

from httpcommon import HttpCommon
from repo import Post, persist_post

thread_reg = re.compile(
    'normalthread_(?P<post_id>[\w\W]*?)">([\w\W]*?)<span id="thread_([\w\W]*?)"><a([\w\W]*?)">(?P<title>[\w\W]*?)</a>([\w\W]*?)uid=([\w\W]*?)">(?P<author_name>[\w\W]*?)</a>([\w\W]*?)<em>(?P<post_time>[\w\W]*?)</em>')
photo_reg = re.compile('file="attachments/([\w\W]*?)"')

cookies = {

}


class Error(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class DiscuzAPI(object):
    async def thread_posts(self, fid, page=1, filter='digest', orderby='dateline'):
        def parse(content):
            raw_threads = re.findall(thread_reg, content)
            threads = []
            for raw_thread in raw_threads:
                thread = {
                    'post_id': int(raw_thread[0]),
                    'title': raw_thread[4],
                    'author_id': raw_thread[6],
                    'author_name': raw_thread[7],
                    'post_time': raw_thread[9]
                }
                threads.append(thread)
            return threads

        content = await HttpCommon.http_get(forum_config['board_url'],
                                            params={'fid': fid, 'filter': filter, 'page': page, 'orderby': orderby})
        print('fetch thread {} succeed!'.format(fid))
        return parse(content)

    async def post_detail(self, tid, all=False):
        try:
            content = await HttpCommon.http_get(forum_config['thread_url'], params={'tid': tid})
            print('fetch post {} succeed!'.format(tid))
            post_photos = re.findall(photo_reg, content)
            sub_post_ids = re.findall(re.compile('id="postmessage_([\w\W]*?)"'), content)
            soup = BeautifulSoup(content, 'lxml')
            post_content = soup.find(id=('postmessage_' + sub_post_ids[0]))
            post_desc = post_content.get_text()

            thread = {
                'post_id': tid,
                'photos': post_photos,
                'content': post_content,
                'desc': post_desc,
                'succeed': True
            }

            if all:
                thread.update({
                    'title': re.findall(re.compile('<h1>([\w\W]*?)</h1>'), content)[0]
                })

            return thread
        except Exception as e:
            print(e)
            return {
                'post_id': tid,
                'succeed': False
            }


class Discuz(DiscuzAPI):
    def __init__(self, concur_req=10, verbose=False):
        self.api = DiscuzAPI()
        self.coro = MyCoro()
        self.loop = asyncio.get_event_loop()
        self.post_exist = 0
        self.break_count_post_exist = 5
        self.verbose = verbose
        self.concur_req = concur_req
        self.semaphore = asyncio.Semaphore(concur_req)
        self.todo = []
        self.pending_data = []

    def set_debug(self, debug=True):
        self.api.set_debug(debug)

    def get_lists(self, fid, start_page, end_page):
        desc = '分类 {}, {} 页 到 {} 页'.format(fid, start_page, end_page)
        items_need_detail = self.coro.set_todo(
            [self.api.thread_posts(fid, page) for page in range(start_page, end_page + 1)]).run(
            desc, self.save_posts)
        return items_need_detail

    def get_detail(self, posts):
        desc = '详情'
        details = self.coro.set_todo([self.api.post_detail(post['post_id']) for post in posts]).run(desc,
                                                                                               self.save_post_detail)
        return details

    @staticmethod
    def trans_lists_to_dict(l):
        data = {}
        for dic in l:
            data.update(dic)

        return data

    def save_posts(self, thread_items):
        if not thread_items or len(thread_items) <= 0:
            self.post_exist = self.break_count_post_exist + 1
            return None

        items_need_detail = []
        for key, item in enumerate(thread_items):
            post = Post.get_or_none(post_id=item['post_id'])
            if post is None:
                post = Post.create(
                    **{k: item[k] for k in ['post_id', 'title', 'author_id', 'author_name', 'post_time']})
                print('save! digest post ', post.post_id)
                items_need_detail.append(item)
            else:
                print('skip! digest post ', item['post_id'])
                self.post_exist += 1
                if not post.photos:
                    items_need_detail.append(item)
        print('Exist digest count {}, Need detail posts count {}'.format(self.post_exist,
                                                                         len(items_need_detail)))
        return items_need_detail

    @staticmethod
    def save_post_detail(item):
        post_id = item['post_id']
        post = Post.get_or_none(post_id=post_id)

        if post.photos:
            print('post {} detail exist '.format(post_id))
            return {
                'post_id': post.post_id,
                'photos': json.loads(post.photos),
                'desc': post.desc,
                'author_id': post.author_id
            }

        if not item['succeed']:
            post.photos = json.dumps([])
            post.save()
            return post

        item['author_id'] = post.author_id
        if post:
            post.content = str(item['content'])
            post.desc = item['desc']
            post.photos = json.dumps(item['photos'])
            post.save()
        else:
            post = Post.create(**{k: item[k] for k in
                                  ['post_id', 'title', 'content', 'desc', 'author_id', 'author_name', 'post_time']})
        print('update detail for ', post_id)

        return post

    def __del__(self):
        self.loop.close()
