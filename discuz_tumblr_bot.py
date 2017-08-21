import json
import tumblpy
from multiprocessing import Pool, Manager
import os

import config
from discuz import Discuz
from repo import Post

MAX_CONCUR = 5


def dd(content):
    print(type(content))
    print(content)
    exit(1)


class TumblrLimitException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


def tumblr_posting(client, discuz_post, my_blog):
    try:
        if discuz_post is None:
            return None

        print('reblog start {}'.format(discuz_post['post_id']))
        post = {
            'type': 'text',
            'native_inline_images': True,
            'title': discuz_post['title'],
            'body': discuz_post['desc'],
            'tags': discuz_post['author_name'],
        }
        res = client.post('post', my_blog, params=post)
    except tumblpy.exceptions.TumblpyError as e:
        if ('your daily post limit' in str(e)):
            raise TumblrLimitException(str(e))
        else:
            print(e)
            print('reblog fail: {}'.format(discuz_post['post_id']))
            Post.update(downloaded=2).where(Post.post_id == discuz_post['post_id']).execute()
    else:
        print('reblog success: {}'.format(res))
        Post.update(downloaded=1).where(Post.post_id == discuz_post['post_id']).execute()


def init_client():
    oauth_config = config.oauth_config
    return tumblpy.Tumblpy(oauth_config['consumer_key'], oauth_config['consumer_secret'],
                           oauth_config['token'], oauth_config['token_secret'])


def reblog(status=0):
    client = init_client()
    offset = 0
    step = 200
    posts = Post.select().where(Post.downloaded == status).order_by(Post.id.desc()).offset(offset).limit(step)
    if posts.count() > 0:
        print('start count {}'.format(len(posts)))
        pool = Pool(10)
        m = Manager()
        event = m.Event()
        for post in posts:
            # reblog_a_blog(client, post)
            pool.apply_async(reblog_a_blog, (client, post, event))
        pool.close()
        event.wait()  # We'll block here until a worker calls `event.set()`
        pool.terminate()
        pool.join()
    else:
        print('no post')


def reblog_a_blog(client, post, event):
    try:
        post = {
            'post_id': post.post_id,
            'title': post.title,
            'desc': post.desc,
            'author_name': post.author_name,
            'photos': json.loads(post.photos),
        }
        format_post = format_discuz_post(post)
        if format_post is None:
            print('skip reblog {}'.format(post['post_id']))
            return None

        for num, desc in enumerate(format_post['contents']):
            reblog_post = dict(post)
            reblog_post['desc'] = desc
            if len(format_post['contents']) > 1:
                reblog_post['title'] += '【{}】'.format(num + 1)
            tumblr_posting(client, reblog_post, config.my_blog)
    except TumblrLimitException as e:
        print(e)
        event.set()
    except Exception as e:
        print(e)


def format_discuz_post(post):
    image_count = 0
    image_total = len(post['photos'])
    if image_total < 5:
        Post.update(downloaded=3).where(Post.post_id == post['post_id']).execute()
        return None
    post['desc'] = '\n'.join(list(filter(lambda line: len(line) > 3, post['desc'].splitlines())))
    desc = ''
    replace = []
    split_count = 100
    split_name = '\n=========================\n'
    for num, line in enumerate(post['desc'].splitlines()):
        line = line.replace('{', '').replace('}', '')

        if num in replace:
            continue
        if '下载 (' in line:
            image_count += 1
            desc += '\n{}'
            replace = [num + 1]

            if image_count % split_count == 0 and (image_total - image_count) > split_count // 2:
                desc += split_name

        else:
            desc = desc + '\n' + line

    if image_total - image_count > 0:
        for i in range(1, image_total - image_count + 1):
            desc += '\n{}'
            if i % split_count == 0 and (image_total - i) > split_count // 2:
                desc += split_name

    post['desc'] = desc.format(
        *('<img src="{}">'.format(config.forum_config['attachment_url'] % photo_id) for photo_id in post['photos']))
    post['contents'] = post['desc'].split(split_name)
    return post


def get_posted_posts():
    with open(config.posts_file, 'r') as f:
        all_posts = json.loads(f.read())
        return all_posts


def add_post_info(all_posts, post_id):
    post_id = int(post_id)
    if post_id not in all_posts:
        all_posts.append(post_id)
    with open(config.posts_file, 'w') as f:
        f.write(json.dumps(all_posts))
    return all_posts


def update_discuz(fids, cookies={}):
    discuz = Discuz(concur_req=MAX_CONCUR)
    discuz.set_cookies(cookies)

    for fid_info in fids:
        if fid_info[0] in [19, 21]:
            discuz.set_cookies({})
        threads_posts = discuz.get_lists(*fid_info)
        for posts in threads_posts:
            discuz.get_detail(posts)


def update_detail_from_database():
    discuz = Discuz(concur_req=MAX_CONCUR)
    offset = 0
    step = 100
    while True:
        posts = Post.select().where(Post.photos >> None).offset(offset).limit(step)
        if posts.count() == 0:
            break
        discuz.get_detail(posts)
        offset += step
        print('offset {}'.format(offset))


if __name__ == '__main__':
    fids = [
        (19, 1, 2, 'digest', 'dateline'),
        (17, 1, 2, 'digest', 'dateline'),
        (4, 1, 2, 'digest', 'dateline'),
        (21, 1, 2, 'digest', 'dateline'),

        # (19, 1, 170, '2592000', 'heats'),
        # (17, 1, 18, '2592000', 'heats'),
        # (4, 1, 51, '2592000', 'heats'),
        # (21, 1, 47, '2592000', 'heats'),
    ]

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.json'), 'r') as f:
        cookies = json.loads(f.read())

    update_discuz(fids, cookies)
    update_detail_from_database()

    reblog()
