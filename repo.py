from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase
import datetime
import os

db = SqliteExtDatabase(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/database.db'))


class BaseModel(Model):
    class Meta:
        database = db

    @classmethod
    def get_or_none(cls, **kwargs):
        try:
            model = cls.get(**kwargs)
        except cls.DoesNotExist:
            return None
        else:
            return model

    def __getitem__(self, item):
        return getattr(self, item)


class Post(BaseModel):
    id = IntegerField(primary_key=True)
    post_id = CharField(null=True, unique=True)
    title = CharField(null=True, default=0)
    content = TextField(null=True)
    desc = TextField(null=True)
    photos = TextField(null=True)
    post_time = CharField(null=True)
    author_name = CharField(null=True)
    author_id = CharField(null=True)
    downloaded = IntegerField(default=0)
    updatetime = DateTimeField(default=datetime.datetime.utcnow)


try:
    db.connect()
    db.create_tables([Post])
except OperationalError:
    pass


def persist_post(post_info):
    try:
        post = Post.get(Post.post_id == post_info['post_id'])
        # print('{} exist, skip'.format(post_info['post_id']))
    except Post.DoesNotExist:
        post = Post.create(**post_info)
        # print('save {}, success'.format(post_info['post_id']))

    return post
