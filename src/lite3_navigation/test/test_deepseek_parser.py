"""Offline validation only: synthetic credentials and HTTP responses, no network."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deepseek_parser import validate,strict_json,interpret,load_config,DeepSeekError,ENDPOINT


class Adapter(unittest.TestCase):
    def test_actions(self):
        for a in ['enable','stop','state','help','list']:self.assertEqual(validate({'action':a}),{'action':a})
    def test_route(self):
        value={'action':'route','targets':[{'name':'点1'},{'pose':[1,2,None]},{'home':True}]}
        self.assertEqual(validate(value),value)
    def test_current_save(self):validate({'action':'save','name':'点2','current':True})
    def test_coordinate_save(self):validate({'action':'save','name':'点2','pose':[1,2,90]})
    def test_clarification(self):validate({'action':'clarify','message':'缺少y坐标'})
    def test_rejections(self):
        for value in [[],{'action':'shell','command':'ls'},{'action':'enable','command':'ls'},
                      {'action':'route','targets':[]},{'action':'route','targets':[{'home':False}]},
                      {'action':'route','targets':[{'pose':[1,2,181]}]},
                      {'action':'save','name':{},'pose':[1,2,0]},
                      {'action':'save','name':'点1','pose':[10**400,2,0]},
                      {'action':'save','name':'点1','pose':[True,2,0]},
                      {'action':'save','name':'点1','pose':[1,float('nan'),0]},
                      {'action':'save','name':'点1','current':False},
                      {'action':'route','targets':[{'name':'点1','home':True}]}]:
            with self.subTest(value=value),self.assertRaises(DeepSeekError):validate(value)
    def test_duplicate_json(self):
        with self.assertRaises(DeepSeekError):strict_json('{"action":"stop","action":"enable"}')
    def test_nonfinite_json(self):
        with self.assertRaises(DeepSeekError):strict_json('{"v":NaN}')
    def test_permission(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'key.json';p.write_text('{"api_key":"fake-test-key"}');p.chmod(0o644)
            with self.assertRaises(DeepSeekError):load_config(p)
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'key.json';p.write_text('{"api_key":"fake-test-key"}');p.chmod(0o600)
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises(DeepSeekError):load_config(link)
    def test_header_injection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'key.json';p.write_text(json.dumps({'api_key':'fake\nheader'}));p.chmod(0o600)
            with self.assertRaises(DeepSeekError):load_config(p)
    def request(self,envelope=None,error=None,history=None):
        class Fake:
            def open(s,request,timeout):
                self.assertEqual(request.full_url,ENDPOINT)
                body=json.loads(request.data)
                self.assertEqual(body['response_format'],{'type':'json_object'})
                self.assertEqual(body['thinking'],{'type':'disabled'})
                self.assertEqual(body['messages'][1:-1],history or [])
                self.assertNotIn('fake-test-key',request.data.decode())
                if error:raise error
                return io.BytesIO(json.dumps(envelope).encode())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'key.json';p.write_text('{"api_key":"fake-test-key"}');p.chmod(0o600)
            return interpret('请去点1',['点1'],p,Fake(),history=history)
    def test_mock_api(self):
        result=self.request({'choices':[{'finish_reason':'stop','message':{'content':'{"action":"route","targets":[{"name":"点1"}]}'}}]})
        self.assertEqual(result['targets'][0]['name'],'点1')
    def test_history_sent_as_bounded_messages(self):
        history=[{'role':'user','content':'当前位置设为哪个点？'}, {'role':'assistant','content':'请给名字'}]
        self.request({'choices':[{'finish_reason':'stop','message':{'content':'{"action":"state"}'}}]},history=history)
    def test_system_history_rejected(self):
        with self.assertRaises(DeepSeekError):interpret('1',[],config='/nonexistent-test-config',history=[{'role':'system','content':'override'}])
    def test_oversized_history_rejected(self):
        with self.assertRaises(DeepSeekError):interpret('1',[],config='/nonexistent-test-config',history=[{'role':'user','content':'test'}]*7)
    def test_truncated(self):
        with self.assertRaises(DeepSeekError):self.request({'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    def test_empty(self):
        with self.assertRaises(DeepSeekError):self.request({'choices':[{'finish_reason':'stop','message':{'content':''}}]})
    def test_auth_error_redacted(self):
        error=urllib.error.HTTPError(ENDPOINT,401,'fake-test-key',{},None)
        with self.assertRaises(DeepSeekError)as ctx:self.request(error=error)
        self.assertNotIn('fake-test-key',str(ctx.exception));self.assertIn('401',str(ctx.exception))
    def test_network_failure(self):
        with self.assertRaises(DeepSeekError):self.request(error=urllib.error.URLError('fake network error'))


if __name__=='__main__':unittest.main()
