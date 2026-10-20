"""Single bounded daemon worker. Completion is consumed only by the ROS thread."""
import queue
import threading
from deepseek_parser import DeepSeekError


class LanguageWorker:
    def __init__(self):
        self.thread=None;self.results=queue.Queue(maxsize=1)

    def submit(self,token,function,*args):
        if self.thread and self.thread.is_alive():return False
        # Poll/discard the previous completion before scheduling another request.
        if not self.results.empty():return False
        def run():
            try:result=(token,function(*args),None)
            except DeepSeekError as error:result=(token,None,str(error))
            except Exception:result=(token,None,'模型请求处理异常，已拒绝本次输入。')
            self.results.put_nowait(result)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start();return True

    def poll(self):
        try:return self.results.get_nowait()
        except queue.Empty:return None
