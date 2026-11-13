import copy,json,unittest,xml.etree.ElementTree as ET
from pathlib import Path
from vi_design import validate_spec,DesignError
class StructuredTests(unittest.TestCase):
 def fixture(self):return json.loads((Path(__file__).parent/'examples/structured_complex.json').read_text())
 def test_actual_structures_emitted(self):
  s,x,t=validate_spec(self.fixture());r=ET.fromstring(x)
  for name in ('For Loop','While Loop','Case Structure','Event Structure'):self.assertTrue(any(e.tag=='Structure' and e.get('_name')==name for e in r.iter()),name)
  for name in ('Create User Event','Generate User Event','Destroy User Event','Register For Events'):self.assertTrue(any(e.get('_name')==name for e in r.iter()),name)
 def test_array_state_and_event_expected(self):
  s,_,_=validate_spec(self.fixture());tests=s['tests'];self.assertEqual(tests[0]['expected']['Corrected'],[0.0,2.0,4.0]);self.assertEqual(tests[3]['expected']['StateTrace'],[0,1,2,0,0]);self.assertEqual(tests[4]['expected']['EventCount'],0)
 def test_wrong_oracle_rejected(self):
  s=self.fixture();s['tests'][0]['expected']={k:0 for k in ['Corrected','Average','Pass','FinalState','EventCount','StateTrace']}
  with self.assertRaises(DesignError):validate_spec(s)
 def test_input_assignment_rejected(self):
  s=self.fixture();s['program']=[{'op':'set','name':'Gain','expression':'2.0'}]
  with self.assertRaises(DesignError):validate_spec(s)
 def test_reserved_event_rejected(self):
  s=self.fixture();s['tests'][0]['inputs']['Commands']=[-2147483648]
  with self.assertRaises(DesignError):validate_spec(s)
 def test_command_budget(self):
  s=self.fixture();s['tests'][0]['inputs']['Commands']=[1]*65
  with self.assertRaises(DesignError):validate_spec(s)
 def test_no_arbitrary_node_or_script(self):
  s=self.fixture();s['program']=[{'op':'shell','command':'id'}]
  with self.assertRaises(DesignError):validate_spec(s)
 def test_while_and_for(self):
  s={'kind':'structured','name':'Bounded','description':'loop','inputs':[{'name':'N','type':'int32','default':4}],'variables':[{'name':'Count','type':'int32','initial':'0'},{'name':'Total','type':'int32','initial':'0'}],'program':[{'op':'for','count':'N','index':'i','body':[{'op':'set','name':'Total','expression':'Total+i'}],'collect':[]},{'op':'while','until':'Count>=3','max_iterations':10,'index':'j','body':[{'op':'set','name':'Count','expression':'Count+1'}]}],'outputs':[{'name':'Sum','expression':'Total'},{'name':'Iterations','expression':'Count'}],'tests':[{'inputs':{'N':4},'expected':{'Sum':6,'Iterations':3}}]};self.assertEqual(validate_spec(s)[0]['tests'][0]['expected']['Sum'],6)
if __name__=='__main__':unittest.main()
