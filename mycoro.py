import asyncio
import tqdm


class MyCoro:
    def run(self, desc=None, handler=None):
        loop = asyncio.get_event_loop()
        self.flush_pending_data()
        data = loop.run_until_complete(self.crawler_coro(self.get_todo(), self.pending_data, handler=handler))
        return data

    async def crawler_coro(self, todo, data=[], desc=None, handler=None):
        todo_iter = asyncio.as_completed(todo)
        todo_iter = tqdm.tqdm(todo_iter, total=len(todo))
        for future in todo_iter:
            res = await future
            if handler is not None:
                res = handler(res)
            data.append(res)

        return data

    def get_todo(self):
        todo = self.todo[:]
        self.flush_todo()
        return todo

    def set_todo(self, todo):
        self.todo = todo
        return self

    def flush_todo(self):
        self.todo = []
        return self

    def get_pending_data(self):
        pending_data = self.pending_data[:]
        self.flush_pending_data()
        return pending_data

    def flush_pending_data(self):
        self.pending_data = []
        return self
