"""Shared and nested state typedef manifests; LabVIEW installs and verifies identity."""
import json,xml.etree.ElementTree as E
from vi_engineering import cluster,default
from vi_gui import INTERNAL
from state_layout import state_layout

def manifest(spec,modules,main):
 token=next(iter(modules)).split('_')[-1].split('.')[0];layout=state_layout(spec)
 types={name:{'fields':[{'name':n,'type':t} for n,t in fields],'values':[dict((v['name'],__import__('vi_structured').expr_value(v['initial'],{})) for v in spec['variables'])[n] for n,t in fields]} for name,fields in layout['groups'].items()}
 types['ApplicationState']={'fields':[dict(name=n,type=t,**({'typedef':n} if n in layout['groups'] else {})) for n,t in layout['physical']],'values':layout['initial']}
 types['DiagnosticsState']={'fields':[{'name':n,'type':t} for n,t in INTERNAL.items() if n!='NI_Ready'],'values':[default(t) for n,t in INTERNAL.items() if n!='NI_Ready']}
 carriers={};bindings=[];nested=[]
 for key,t in types.items():
  name=key+'_'+token;t['file']=name+'.ctl';t['carrier']=name+'_Carrier.vi'
  root=E.Element('VI',{'_name':t['carrier'],'description':'Single-control carrier for native shared typedef creation.'});E.SubElement(root,'Control',{'_name':key,'type':cluster([(f['name'],f['type']) for f in t['fields']]),'value':json.dumps(t['values'],separators=(',',':')),'uid':'1','uid_parent':'root','outputs':'value:1.v'})
  carriers[t['carrier']]=E.tostring(root,encoding='unicode')
 for group in layout['groups']:nested.append({'parent':'ApplicationState','field':group,'typedef':group})
 for name,xml in modules.items():
  for e in E.fromstring(xml).iter():
   if e.tag not in ('Control','Indicator'):continue
   key='ApplicationState' if e.get('_name') in ('StateIn','StateOut') else 'DiagnosticsState' if e.get('_name') in ('DiagnosticsIn','DiagnosticsOut') else None
   if key:bindings.append({'file':'Modules/'+name,'object':e.get('_name'),'typedef':key,'constant':False})
 bindings += [{'file':main,'object':key+'Seed','typedef':key,'constant':True} for key in ('ApplicationState','DiagnosticsState')]
 return {'types':types,'bindings':bindings,'nested_bindings':nested},carriers

def instance_count(types,key):return 1+sum(instance_count(types,f['typedef']) for f in types[key]['fields'] if f.get('typedef'))

def verify_field_tree(tree,definition,types):
 while tree.get('Type')=='TypeDef':tree=next(e for e in tree if e.tag=='TypeDesc')
 if tree.get('Type')!='Cluster':raise ValueError('状态不是Cluster')
 fields=[e for e in tree if e.tag=='TypeDesc'];expected=definition['fields']
 if len(fields)!=len(expected):raise ValueError('状态字段数量不同步')
 basic={'string':'String','double':'NumFloat64','int32':'NumInt32','bool':'Boolean','array{double}':'Array','array{int32}':'Array'}
 for e,f in zip(fields,expected):
  inner_label=next((c.get('Label') for c in e if c.tag=='TypeDesc'),None) if e.get('Type')=='TypeDef' else None
  if (e.get('Label') or inner_label)!=f['name']:raise ValueError('状态字段名称不同步：'+f['name'])
  if f.get('typedef'):
   if e.get('Type')!='TypeDef':raise ValueError('嵌套字段未链接typedef：'+f['name'])
   verify_field_tree(e,types[f['typedef']],types)
  elif f['type'].startswith('ref{'):
   refkind=f['type'].split('{',1)[1].split('}',1)[0]
   if e.get('Type')!='Refnum' or e.get('RefType')!={'Queue':'Queue','ByteStream':'ByteStream'}.get(refkind,refkind):raise ValueError('引用字段类型不同步：'+f['name'])
  elif e.get('Type')!=basic[f['type']]:raise ValueError('状态字段类型不同步：'+f['name'])
  elif f['type'].startswith('array{'):
   element=next(c for c in e if c.tag=='TypeDesc');expected_element='NumFloat64' if f['type']=='array{double}' else 'NumInt32'
   if element.get('Type')!=expected_element:raise ValueError('状态数组元素类型不同步')
