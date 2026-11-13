import unittest
from vi_design import validate_spec,DesignError,import_aixml,model_design
import json
class DesignTests(unittest.TestCase):
 def base(self,expr='x*2+1'):
  return {'name':'General','description':'test','inputs':[{'name':'x','type':'double','default':2}], 'outputs':[{'name':'Y','expression':expr}],'tests':[{'inputs':{'x':2}}]}
 def test_composed_math(self):
  s,x,t=validate_spec(self.base('(x - 0.2) * 5 / 2'));self.assertEqual(s['tests'][0]['expected']['Y'],4.5);self.assertIn('_name="Divide"',x)
 def test_condition_and_bool(self):
  s,x,t=validate_spec(self.base('0 if x < 0 else clamp(x,0,1)'));self.assertEqual(s['tests'][0]['expected']['Y'],1);self.assertIn('_name="Select"',x)
 def test_chained(self):self.assertTrue(validate_spec(self.base('0 <= x <= 3'))[0]['tests'][0]['expected']['Y'])
 def test_reject_calls_and_attributes(self):
  for e in ["__import__('os').system('id')",'x.real','open(x)','[x]','x[0]','lambda: x']:
   with self.subTest(e=e),self.assertRaises(DesignError):validate_spec(self.base(e))
 def test_type_error(self):
  with self.assertRaises(DesignError):validate_spec(self.base('x and True'))
 def test_no_hidden_divide_zero(self):
  with self.assertRaises(DesignError):validate_spec(self.base('1 if x == 2 else 1/(x-2)'))
 def test_oracle_checks_model(self):
  s=self.base();s['tests'][0]['expected']={'Y':99}
  with self.assertRaises(DesignError):validate_spec(s)
 def test_roundtrip(self):
  s,x,t=validate_spec(self.base('abs(x)*2+sqrt(x)'));s2,x2,t2=import_aixml(x);self.assertEqual(s['tests'][0]['expected'],s2['tests'][0]['expected'])
 def test_refuse_unknown_structures(self):
  with self.assertRaises(DesignError):import_aixml('<VI><Structure _name="While Loop"/></VI>')
 def test_node_budget(self):
  with self.assertRaises(DesignError):validate_spec(self.base('max('+','.join(['x']*8)+')'))
 def test_independent_outputs(self):
  s=self.base();s['outputs']=[{'name':'Value','expression':'x*2'},{'name':'Pass','expression':'Value >= 0'}];v=validate_spec(s);self.assertEqual(v[0]['tests'][0]['expected'],{'Value':4,'Pass':True})
 def test_connector_roundtrip(self):
  s=self.base();s['connector']={'x':0,'Y':4};s['connector_pattern']=4833
  a,x,t=validate_spec(s);b,_,_=import_aixml(x);self.assertEqual(b['connector'],s['connector'])
 def test_model_repairs_invalid_design(self):
  bad=self.base();bad['tests'][0]['expected']={'Y':123};answers=iter([bad,self.base()]);calls=[]
  def model(m):calls.append(m);return {'reply':json.dumps(next(answers))}
  out=model_design('test',model)[0];self.assertEqual(out['tests'][0]['expected']['Y'],5);self.assertEqual(len(calls),2)
 def test_modify_preserves_connector(self):
  current=validate_spec(self.base())[0];current['connector']={'x':0,'Y':4}
  result=model_design('change gain',lambda m:{'reply':json.dumps(self.base('x*3'))},current)[0]
  self.assertEqual(result['connector'],current['connector'])
if __name__=='__main__':unittest.main()
