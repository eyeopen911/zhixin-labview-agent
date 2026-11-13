"""Trusted VI Server helpers for actual .ctl creation, linking, and independent inspection."""
import pathlib,xml.etree.ElementTree as E
from build_gui_helpers import base,el,common,err as basic_err
def err(r,net):
 basic_err(r,net)
 n=r.find("Node[@uid='90']");n.set("fields","status,code,source");n.set("outputs",n.get("outputs")+",source:90.source");el(r,"Indicator",93,_name="Source",type="string",value="",inputs="value:90.source")
ROOT=pathlib.Path(__file__).resolve().parents[1];OUT=ROOT/'gui-tools'
src=ROOT/'tools/labview-mcp-source/scripts/lvtd_make_typedef.xml';r=E.fromstring(src.read_text());r.set('_name','CreateStateTypedef.vi');(OUT/'CreateStateTypedef.aixml').write_text(E.tostring(r,encoding='unicode'))
def save(r,name):r.set('_name',name+'.vi');(OUT/(name+'.aixml')).write_text(E.tostring(r,encoding='unicode'))
def target():
 r=base('Target');common(r);el(r,'Control',4,_name='ObjectName',type='string',value='',outputs='value:4.v');el(r,'Control',5,_name='TypedefPath',type='string',value='',outputs='value:5.v');el(r,'Node',6,_name='String To Path',inputs='string:5.v',outputs='path:6.p');return r
def loop(r,u,source):
 f=el(r,'Structure',u,_name='For Loop',count='',maxin='',maxout='')
 E.SubElement(f,'Tunnel',{'_id':'In1','inputs':'value:'+source,'outputs':'value:'+str(u+1)+'.ref','mode':'index','uid':str(u+1),'uid_parent':str(u)})
 return f
def inner(f,tag,u,**a):return E.SubElement(f,tag,dict(a,uid=str(u),uid_parent=f.get('uid')))
def tunnel(f,tid,u,**a):return inner(f,'Tunnel',u,_id=tid,**a)
def bind(constant=False):
 r=target();kind='Constant' if constant else 'Control'
 el(r,'Node',7,_name='Property Node',type='{LV.VI}',fields='read+'+('Block Diagram' if constant else 'Front Panel'),inputs='reference:3.ref,error in (no error):3.err',outputs=('Block Diagram' if constant else 'Front Panel')+':7.owner,error out:7.err')
 el(r,'Node',8,_name='Property Node',type='{LV.Diagram}' if constant else '{LV.Panel}',fields='read+'+('All Objects[]' if constant else 'Controls[]'),inputs='reference:7.owner,error in (no error):7.err',outputs=('All Objects[]' if constant else 'Controls[]')+':8.objects,error out:8.err')
 f=loop(r,10,'8.objects');tunnel(f,'In2',12,inputs='value:4.v',outputs='value:12.name');tunnel(f,'In3',13,inputs='value:6.p',outputs='value:13.path')
 # Label reads on non-constant objects fail harmlessly and yield empty names.
 ref='11.ref'
 if constant:
  el(r,'Constant',9,type='ref{LV.Constant}',value='',outputs='value:9.cls');tunnel(f,'In4',14,inputs='value:9.cls',outputs='value:14.cls');inner(f,'Node',15,_name='To More Specific Class',inputs='reference:11.ref,target class:14.cls,error in:',outputs='specific class reference:15.ref,error out:');ref='15.ref'
 inner(f,'Node',16,_name='Property Node',type='{LV.'+kind+'}',fields='read+Label.Text',inputs='reference:'+ref+',error in (no error):',outputs='Label.Text:16.name,error out:')
 inner(f,'Node',17,_name='Equal?',inputs='x:16.name,y:12.name',outputs='x = y?:17.eq')
 case=inner(f,'Structure',20,_name='Case Structure',selectin='17.eq');tunnel(case,'In1',21,inputs='value:'+ref);tunnel(case,'In2',22,inputs='value:13.path')
 for truth in ('False','True'):
  fr=inner(case,'CaseFrame',30 if truth=='False' else 40,selector=truth,selectout='')
  if truth=='True':
   tunnel(fr,'In1',41,outputs='value:41.ref');tunnel(fr,'In2',42,outputs='value:42.path');inner(fr,'Node',43,_name='Invoke Node',type='{LV.'+kind+'}',target='Replace',inputs='reference:41.ref,error in (no error):,Style:,Path:42.path,PaletteString:',outputs='reference out:,error out:43.err');inner(fr,'Node',44,_name='Unbundle By Name',fields='code',inputs='input cluster:43.err',outputs='code:44.code');inner(fr,'Constant',45,type='int32',value='1',outputs='value:45.count');tunnel(fr,'OutCode',46,inputs='value:44.code');tunnel(fr,'OutCount',47,inputs='value:45.count')
  else:
   inner(fr,'Constant',31,type='int32',value='0',outputs='value:31.zero');tunnel(fr,'OutCode',32,inputs='value:31.zero');tunnel(fr,'OutCount',33,inputs='value:31.zero')
 tunnel(case,'OutCode',50,outputs='value:50.code');tunnel(case,'OutCount',51,outputs='value:51.count');tunnel(f,'OutCodes',52,inputs='value:50.code',outputs='value:52.codes',mode='index');tunnel(f,'OutCounts',53,inputs='value:51.count',outputs='value:53.counts',mode='index')
 el(r,'Node',60,_name='Add Array Elements',inputs='numeric array:53.counts',outputs='sum:60.n');el(r,'Indicator',61,_name='BoundCount',type='int32',value='0',inputs='value:60.n');el(r,'Indicator',62,_name='ReplaceCodes',type='array{int32}',value='[]',inputs='value:52.codes')
 # Link the save to completion of Replace iterations through an error-cluster bundle.
 el(r,'Constant',63,type='cluster{bool.status,int32.code,string.source}',value='[false,0,]',outputs='value:63.err');el(r,'Node',66,_name='Subtract',inputs='x:60.n,y:60.n',outputs='x-y:66.zero');el(r,'Node',64,_name='Bundle By Name',fields='code',inputs='input cluster:63.err,code:66.zero',outputs='output cluster:64.err')
 el(r,'Node',65,_name='Invoke Node',type='{LV.VI}',target='Save.Instrument',inputs='reference:3.ref,error in (no error):64.err,Path to saved file:,Save a Copy:,Without Diagram:',outputs='error out:65.err,reference out:');err(r,'65.err');save(r,'BindStateConstant' if constant else 'BindStateControl')
bind();bind(True)
# Independent readback of actual typedef identity and member names.
r=base('InspectStateTypes');common(r);el(r,'Node',4,_name='Property Node',type='{LV.VI}',fields='read+Front Panel',inputs='reference:3.ref,error in (no error):3.err',outputs='Front Panel:4.fp,error out:4.err');el(r,'Node',5,_name='Property Node',type='{LV.Panel}',fields='read+Controls[]',inputs='reference:4.fp,error in (no error):4.err',outputs='Controls[]:5.cs,error out:5.err');el(r,'Constant',6,type='ref{LV.Cluster}',value='',outputs='value:6.cls')
f=loop(r,10,'5.cs');tunnel(f,'In2',12,inputs='value:6.cls',outputs='value:12.cls')
inner(f,'Node',13,_name='Property Node',type='{LV.Control}',fields='read+Label.Text,read+Is Typedef?,read+Typedef:Path',inputs='reference:11.ref,error in (no error):',outputs='Label.Text:13.name,Is Typedef?:13.kind,Typedef:Path:13.path,error out:')
inner(f,'Node',14,_name='Path To String',inputs='path:13.path',outputs='string:14.path');inner(f,'Node',15,_name='To More Specific Class',inputs='reference:11.ref,target class:12.cls,error in:',outputs='specific class reference:15.ref,error out:');inner(f,'Node',16,_name='Property Node',type='{LV.Cluster}',fields='read+Controls[]',inputs='reference:15.ref,error in (no error):',outputs='Controls[]:16.children,error out:')
f2=inner(f,'Structure',20,_name='For Loop',count='',maxin='',maxout='');tunnel(f2,'In1',21,inputs='value:16.children',outputs='value:21.ref',mode='index');inner(f2,'Node',22,_name='Property Node',type='{LV.Control}',fields='read+Label.Text',inputs='reference:21.ref,error in (no error):',outputs='Label.Text:22.name,error out:');tunnel(f2,'Out1',23,inputs='value:22.name',outputs='value:23.names',mode='index');inner(f,'Constant',26,type='string',value='%s',outputs='value:26.fmt');inner(f,'Constant',24,type='string',value='|',outputs='value:24.sep');inner(f,'Node',25,_name='Array To Spreadsheet String',inputs='array:23.names,format string:26.fmt,delimiter (Tab):24.sep',outputs='spreadsheet string:25.fields')
for u,name,net,t in [(30,'Names','13.name','array{string}'),(31,'Kinds','13.kind','array{uint32}'),(32,'Paths','14.path','array{string}'),(33,'Fields','25.fields','array{string}')]:
 tunnel(f,'Out'+name,u,inputs='value:'+net,outputs='value:'+str(u)+'.out',mode='index');el(r,'Indicator',u+30,_name=name,type=t,value='[]',inputs='value:'+str(u)+'.out')
err(r,'5.err');save(r,'InspectStateTypes')
# Same independent census for root block-diagram constants.
r2=E.fromstring(E.tostring(r,encoding='unicode'))
for n in r2.iter('Node'):
 if n.get('uid')=='4':n.set('fields','read+Block Diagram');n.set('outputs','Block Diagram:4.fp,error out:4.err')
 if n.get('uid')=='5':n.set('type','{LV.Diagram}');n.set('fields','read+All Objects[]');n.set('outputs','All Objects[]:5.cs,error out:5.err')
 if n.get('uid')=='13':n.set('type','{LV.Constant}');n.set('inputs','reference:92.ref,error in (no error):')
 if n.get('uid')=='15':n.set('inputs','reference:92.ref,target class:12.cls,error in:')
 if n.get('uid')=='16':n.set('type','{LV.ClusterConstant}');n.set('fields','read+Elements[]');n.set('outputs','Elements[]:16.children,error out:')
 if n.get('uid')=='22':n.set('type','{LV.Constant}')
r2.find("Constant[@uid='6']").set('type','ref{LV.ClusterConstant}')
el(r2,'Constant',90,type='ref{LV.Constant}',value='',outputs='value:90.cls')
f=r2.find("Structure[@uid='10']");tunnel(f,'In3',91,inputs='value:90.cls',outputs='value:91.cls');cast=inner(f,'Node',92,_name='To More Specific Class',inputs='reference:11.ref,target class:91.cls,error in:',outputs='specific class reference:92.ref,error out:');save(r2,'InspectStateConstants')
# Edit only the typedef definition; consumers are never rewritten by this helper.
r=base('RenameTypedefField');common(r)
el(r,'Control',4,_name='FieldName',type='string',value='',outputs='value:4.name');el(r,'Control',5,_name='NewFieldName',type='string',value='',outputs='value:5.name');el(r,'Constant',6,type='ref{LV.Cluster}',value='',outputs='value:6.cls')
el(r,'Node',7,_name='Property Node',type='{LV.VI}',fields='read+Front Panel',inputs='reference:3.ref,error in (no error):3.err',outputs='Front Panel:7.fp,error out:7.err');el(r,'Node',8,_name='Property Node',type='{LV.Panel}',fields='read+Controls[]',inputs='reference:7.fp,error in (no error):7.err',outputs='Controls[]:8.cs,error out:8.err');el(r,'Node',9,_name='Index Array',inputs='array:8.cs,index:',outputs='element:9.ref');el(r,'Node',10,_name='To More Specific Class',inputs='reference:9.ref,target class:6.cls,error in:8.err',outputs='specific class reference:10.ref,error out:10.err');el(r,'Node',11,_name='Property Node',type='{LV.Cluster}',fields='read+Controls[]',inputs='reference:10.ref,error in (no error):10.err',outputs='Controls[]:11.cs,error out:11.err')
f=loop(r,20,'11.cs');inner(f,'Node',22,_name='Property Node',type='{LV.Control}',fields='read+Label.Text',inputs='reference:21.ref,error in (no error):',outputs='Label.Text:22.name,error out:');tunnel(f,'Out1',23,inputs='value:22.name',outputs='value:23.names',mode='index')
el(r,'Node',30,_name='Search 1D Array',inputs='1D array:23.names,element:4.name,start index (0):',outputs='index of element:30.i');el(r,'Node',31,_name='Index Array',inputs='array:11.cs,index:30.i',outputs='element:31.ref');el(r,'Node',32,_name='Property Node',type='{LV.Control}',fields='write+Label.Text',inputs='reference:31.ref,error in (no error):11.err,Label.Text:5.name',outputs='reference out:,error out:32.err');el(r,'Node',33,_name='Invoke Node',type='{LV.VI}',target='Save.Instrument',inputs='reference:3.ref,error in (no error):32.err,Path to saved file:,Save a Copy:,Without Diagram:',outputs='reference out:,error out:33.err');err(r,'33.err');el(r,'Indicator',34,_name='FieldIndex',type='int32',value='-1',inputs='value:30.i');save(r,'RenameTypedefField')
# Bind one inner cluster in a parent .ctl to a child .ctl before binding any consumers.
r=E.fromstring((OUT/'BindStateControl.aixml').read_text());el(r,'Constant',200,type='ref{LV.Cluster}',value='',outputs='value:200.cls');el(r,'Node',201,_name='Index Array',inputs='array:8.objects,index:',outputs='element:201.ref');el(r,'Node',202,_name='To More Specific Class',inputs='reference:201.ref,target class:200.cls,error in:8.err',outputs='specific class reference:202.ref,error out:202.err');el(r,'Node',203,_name='Property Node',type='{LV.Cluster}',fields='read+Controls[]',inputs='reference:202.ref,error in (no error):202.err',outputs='Controls[]:203.cs,error out:203.err');r.find("Structure[@uid='10']/Tunnel[@uid='11']").set('inputs','value:203.cs');save(r,'BindNestedStateControl')
# Inspect a named nested cluster instance in a control or diagram constant.
for constant in (False,True):
 r=base('Nested');common(r);el(r,'Control',4,_name='ObjectName',type='string',value='',outputs='value:4.name');el(r,'Control',5,_name='GroupName',type='string',value='',outputs='value:5.name');kind='Constant' if constant else 'Control';cl='ClusterConstant' if constant else 'Cluster'
 el(r,'Constant',6,type='ref{LV.'+cl+'}',value='',outputs='value:6.cls');el(r,'Node',7,_name='Property Node',type='{LV.VI}',fields='read+'+('Block Diagram' if constant else 'Front Panel'),inputs='reference:3.ref,error in (no error):3.err',outputs=('Block Diagram' if constant else 'Front Panel')+':7.owner,error out:7.err');el(r,'Node',8,_name='Property Node',type='{LV.Diagram}' if constant else '{LV.Panel}',fields='read+'+('All Objects[]' if constant else 'Controls[]'),inputs='reference:7.owner,error in (no error):7.err',outputs=('All Objects[]' if constant else 'Controls[]')+':8.cs,error out:8.err')
 if constant:el(r,'Constant',9,type='ref{LV.Constant}',value='',outputs='value:9.cls')
 f=loop(r,10,'8.cs');ref='11.ref'
 if constant:
  tunnel(f,'In2',12,inputs='value:9.cls',outputs='value:12.cls');inner(f,'Node',13,_name='To More Specific Class',inputs='reference:11.ref,target class:12.cls,error in:',outputs='specific class reference:13.ref,error out:');ref='13.ref'
 inner(f,'Node',14,_name='Property Node',type='{LV.'+kind+'}',fields='read+Label.Text',inputs='reference:'+ref+',error in (no error):',outputs='Label.Text:14.name,error out:');tunnel(f,'Out1',15,inputs='value:14.name',outputs='value:15.names',mode='index')
 el(r,'Node',20,_name='Search 1D Array',inputs='1D array:15.names,element:4.name,start index (0):',outputs='index of element:20.i');el(r,'Node',21,_name='Index Array',inputs='array:8.cs,index:20.i',outputs='element:21.ref');el(r,'Node',22,_name='To More Specific Class',inputs='reference:21.ref,target class:6.cls,error in:',outputs='specific class reference:22.ref,error out:22.err')
 children='Elements[]' if constant else 'Controls[]';el(r,'Node',23,_name='Property Node',type='{LV.'+cl+'}',fields='read+'+children,inputs='reference:22.ref,error in (no error):22.err',outputs=children+':23.cs,error out:23.err')
 f=loop(r,30,'23.cs');inner(f,'Node',32,_name='Property Node',type='{LV.'+kind+'}',fields='read+Label.Text',inputs='reference:31.ref,error in (no error):',outputs='Label.Text:32.name,error out:');tunnel(f,'Out1',33,inputs='value:32.name',outputs='value:33.names',mode='index')
 el(r,'Node',40,_name='Search 1D Array',inputs='1D array:33.names,element:5.name,start index (0):',outputs='index of element:40.i');el(r,'Node',41,_name='Index Array',inputs='array:23.cs,index:40.i',outputs='element:41.ref');el(r,'Node',42,_name='Property Node',type='{LV.'+kind+'}',fields='read+Is Typedef?,read+Typedef:Path',inputs='reference:41.ref,error in (no error):23.err',outputs='Is Typedef?:42.kind,Typedef:Path:42.path,error out:42.err');el(r,'Node',43,_name='Path To String',inputs='path:42.path',outputs='string:43.path');el(r,'Node',44,_name='To More Specific Class',inputs='reference:41.ref,target class:6.cls,error in:42.err',outputs='specific class reference:44.ref,error out:44.err');el(r,'Node',45,_name='Property Node',type='{LV.'+cl+'}',fields='read+'+children,inputs='reference:44.ref,error in (no error):44.err',outputs=children+':45.cs,error out:45.err')
 f=loop(r,50,'45.cs');inner(f,'Node',52,_name='Property Node',type='{LV.'+kind+'}',fields='read+Label.Text',inputs='reference:51.ref,error in (no error):',outputs='Label.Text:52.name,error out:');tunnel(f,'Out1',53,inputs='value:52.name',outputs='value:53.names',mode='index')
 el(r,'Indicator',60,_name='Fields',type='array{string}',value='[]',inputs='value:53.names');el(r,'Indicator',61,_name='Kind',type='uint32',value='0',inputs='value:42.kind');el(r,'Indicator',62,_name='Path',type='string',value='',inputs='value:43.path');err(r,'45.err');save(r,'InspectNestedConstant' if constant else 'InspectNestedControl')
