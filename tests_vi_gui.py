import copy,json,unittest,xml.etree.ElementTree as ET
from pathlib import Path
from vi_design import validate_spec,DesignError
class GuiTests(unittest.TestCase):
 def fixture(self):return json.loads((Path(__file__).parent/'examples/gui_timed_sampler.json').read_text())
 def test_true_button_frames_and_timeout_wire(self):
  s,x,t=validate_spec(self.fixture());root=ET.fromstring(x);event=next(e for e in root.iter() if e.get('_name')=='Event Structure');self.assertTrue(event.get('timeout'))
  for name in ('Start','Stop','Reset','Exit'):self.assertTrue(any('"'+name+'"' in f.get('selector','') and 'Value Change' in f.get('selector','') for f in event))
 def test_live_controls_and_indicators(self):
  s,x,t=validate_spec(self.fixture());root=ET.fromstring(x);loop=next(e for e in root if e.get('_name')=='While Loop');self.assertTrue(any(e.tag=='Control' and e.get('_name')=='IntervalMs' for e in loop));self.assertTrue(any(e.tag=='Indicator' and e.get('_name')=='TickCount' for e in loop))
 def test_expected_result(self):self.assertEqual(validate_spec(self.fixture())[0]['tests'][0]['expected'],{'TickCount':3,'Values':[2.0,4.0,6.0],'Average':4.0,'Running':False,'ResetCount':1})
 def test_missing_exit(self):
  s=self.fixture();s['tests'][0]['actions'].pop()
  with self.assertRaises(DesignError):validate_spec(s)
 def test_pause_must_hold(self):
  s=self.fixture();s['buttons'][1]['body']=[]
  with self.assertRaises(DesignError):validate_spec(s)
 def test_reset_must_clear(self):
  s=self.fixture();s['buttons'][2]['body']=[v for v in s['buttons'][2]['body'] if v['name']!='Buffer']
  with self.assertRaises(DesignError):validate_spec(s)
 def test_invalid_interval(self):
  s=self.fixture();s['tests'][0]['inputs']['IntervalMs']=0
  with self.assertRaises(DesignError):validate_spec(s)
 def test_no_script_action(self):
  s=self.fixture();s['buttons'][0]['body']=[{'op':'shell','command':'id'}]
  with self.assertRaises(DesignError):validate_spec(s)
 def test_no_input_dependent_seed(self):
  s=self.fixture();s['variables'][0]['initial']='int32(Gain)'
  with self.assertRaises(DesignError):validate_spec(s)
if __name__=='__main__':unittest.main()
