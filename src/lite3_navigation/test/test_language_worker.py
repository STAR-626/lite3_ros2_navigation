import threading
import time
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from language_worker import LanguageWorker
from deepseek_parser import DeepSeekError


class Worker(unittest.TestCase):
    def poll(self,w):
        end=time.monotonic()+2
        while time.monotonic()<end:
            value=w.poll()
            if value is not None:return value
            time.sleep(.005)
        self.fail('worker result timeout')
    def test_nonblocking_singleflight(self):
        gate=threading.Event();w=LanguageWorker();start=time.monotonic()
        def work():gate.wait(1);return {'action':'stop'}
        self.assertTrue(w.submit('one',work));self.assertLess(time.monotonic()-start,.1)
        self.assertFalse(w.submit('two',work));gate.set()
        self.assertEqual(self.poll(w),('one',{'action':'stop'},None))
    def test_known_error(self):
        w=LanguageWorker()
        def work():raise DeepSeekError('模拟认证错误')
        w.submit('one',work);self.assertEqual(self.poll(w)[2],'模拟认证错误')
    def test_unexpected_error_redacted(self):
        w=LanguageWorker()
        def work():raise RuntimeError('synthetic-secret-not-for-output')
        w.submit('one',work);self.assertNotIn('synthetic-secret',self.poll(w)[2])


if __name__=='__main__':unittest.main()
