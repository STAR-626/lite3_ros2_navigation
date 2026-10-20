"""Native protocol and bounded tool loop; fake HTTP credentials, no network/ROS."""
import io,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from agent_tools import TOOLS,parse_message,validate_call
from deepseek_agent import request_turn
from deepseek_parser import DeepSeekError


def call(name,args,ident='call_1'):
    return {'id':ident,'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}

class Tools(unittest.TestCase):
    def test_capability_registry_has_no_shell_or_unlock(self):
        names={t['function']['name']for t in TOOLS}
        self.assertIn('approach_object',names);self.assertIn('get_environment',names)
        self.assertFalse(names.intersection({'shell','exec','enable_navigation','confirm'}))
    def test_tool_schema_is_closed(self):
        for t in TOOLS:self.assertFalse(t['function']['parameters']['additionalProperties'])
    def test_valid_calls(self):
        for name,args in [('get_environment',{}),('get_environment',{'kind':'model','category':'墙体'}),('get_robot_state',{}),('approach_object',{'object':'model:wall_east'}),('navigate_to',{'pose':[3,2,None]}),('navigate_to',{'name':'点1'}),('save_place',{'name':'点1','current':True}),('delete_places',{'all':True}),('delete_places',{'names':['点1','点2']}),('annotate_object',{'object':'shelf_1','description':'巡检'})]:
            with self.subTest(name=name):validate_call(name,args)
    def test_invalid_calls(self):
        for name,args in [('exec',{'cmd':'ls'}),('get_robot_state',{'extra':True}),('navigate_to',{}),('navigate_to',{'name':'点1','pose':[1,2,0]}),('delete_places',{'all':False}),('delete_places',{'names':['点1','点1']}),('delete_places',{'names':[True]}),('delete_places',{'all':True,'names':['点1']}),('save_place',{'name':'家','current':True}),('approach_object',{'object':'shelf_1','clearance':float('nan')})]:
            with self.subTest(name=name),self.assertRaises(ValueError):validate_call(name,args)
    def test_batch_whole_validated_before_return(self):
        msg={'content':'先去东墙再去货架1','tool_calls':[call('approach_object',{'object':'model:wall_east'}),call('approach_object',{'object':'model:shelf_1'},'call_2')]}
        self.assertEqual(len(parse_message(msg,'tool_calls')['tool_calls']),2)
        msg['tool_calls'][1]=call('exec',{},'call_2')
        with self.assertRaises(DeepSeekError):parse_message(msg,'tool_calls')
    def test_duplicate_call_id(self):
        with self.assertRaises(DeepSeekError):parse_message({'tool_calls':[call('get_environment',{}),call('get_robot_state',{})]},'tool_calls')
    def test_duplicate_json_and_nonfinite(self):
        for raw in ['{"all":true,"all":false}','{"pose":[1,NaN,0]}']:
            c=call('delete_places',{});c['function']['arguments']=raw
            with self.assertRaises(DeepSeekError):parse_message({'tool_calls':[c]},'tool_calls')
    def test_truncated_or_empty(self):
        for msg,finish in [({'content':'完成'},'length'),({'content':''},'stop'),({'tool_calls':[]},'tool_calls')]:
            with self.assertRaises(DeepSeekError):parse_message(msg,finish)
    def test_multiple_queries_and_tool_results_forwarded(self):
        messages=[{'role':'user','content':'先去东墙，再去货架1'},
                  {'role':'assistant','content':'','tool_calls':[call('get_environment',{})]},
                  {'role':'tool','tool_call_id':'call_1','content':'{"objects":[{"id":"model:wall_east","pose_world":[5,0,0,0]}]}'}]
        class Fake:
            def open(s,request,timeout):
                body=json.loads(request.data)
                self.assertEqual(body['messages'][1:],messages);self.assertEqual(body['tools'],TOOLS)
                self.assertNotIn('response_format',body);self.assertNotIn('test-key',request.data.decode())
                return io.BytesIO(json.dumps({'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[call('approach_object',{'object':'model:wall_east'})]}}]}).encode())
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'fake.json';p.write_text('{"api_key":"test-key"}');p.chmod(0o600)
            self.assertEqual(request_turn(messages,p,Fake())['tool_calls'][0]['function']['name'],'approach_object')
    def test_request_size_limit_before_credentials(self):
        with self.assertRaises(DeepSeekError):request_turn([{'role':'user','content':'x'*160001}],config='/not-a-real-file')

if __name__=='__main__':unittest.main()
