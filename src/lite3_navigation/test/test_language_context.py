import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from language_context import ClarificationContext,normalize_names,describe,navigation_problem


class Context(unittest.TestCase):
    def test_empty(self):self.assertEqual(ClarificationContext().messages(),[])
    def test_clarification_chain(self):
        c=ClarificationContext();c.remember('把当前位置设成点1或家','请选一个名称。');c.remember('保存为','保存为什么名字？')
        h=c.messages();self.assertEqual(len(h),4);self.assertEqual(h[0]['content'],'把当前位置设成点1或家')
        self.assertEqual(json.loads(h[-1]['content'])['action'],'clarify')
    def test_bounded(self):
        c=ClarificationContext()
        for i in range(5):c.remember(str(i),'问题')
        self.assertEqual(len(c.messages()),6);self.assertEqual(c.messages()[0]['content'],'2')
    def test_expiry(self):
        now=[10.];c=ClarificationContext(clock=lambda:now[0]);c.remember('当前位置','叫什么？');now[0]+=91
        self.assertEqual(c.messages(),[])
    def test_clear(self):
        c=ClarificationContext();c.remember('位置','问题');c.clear();self.assertEqual(c.messages(),[])
    def test_digit_reference_alias(self):
        v={'action':'route','targets':[{'name':'1'},{'name':'点一'},{'name':'二'}]}
        self.assertEqual([t['name']for t in normalize_names(v,['点1','点2'])['targets']],['点1','点1','点2'])
        self.assertEqual(v['targets'][0]['name'],'1')
    def test_exact_name_wins(self):
        self.assertEqual(normalize_names({'action':'show','name':'1'},['1','点1'])['name'],'1')
    def test_no_invented_name(self):
        self.assertEqual(normalize_names({'action':'show','name':'3'},['点1'])['name'],'3')
    def test_save_not_silently_renamed(self):
        self.assertEqual(normalize_names({'action':'save','name':'1','current':True},['点1'])['name'],'1')
    def test_disabled_reason(self):
        state=dict(navigation_enabled=False,busy=False,fault_latched=False,switch_pending=False)
        self.assertIn('总开关当前关闭',navigation_problem(state))
        state['navigation_enabled']=True;self.assertIsNone(navigation_problem(state))
    def test_other_state_reasons(self):
        for key,text in [('busy','其他任务'),('fault_latched','故障锁定'),('switch_pending','尚未完成')]:
            state=dict(navigation_enabled=True,busy=False,fault_latched=False,switch_pending=False);state[key]=True
            self.assertIn(text,navigation_problem(state))
    def test_malformed_state(self):
        with self.assertRaises(ValueError):navigation_problem({'busy':'false'})
    def test_friendly_description(self):
        self.assertIn('当前位置',describe({'action':'save','name':'点1','current':True}))
        self.assertIn('点1 → 原点',describe({'action':'route','targets':[{'name':'点1'},{'home':True}]}))


if __name__=='__main__':unittest.main()
