"""Backend-owned engineering layout and state-cluster modularization for GUI IR."""
import ast,copy,hashlib,json,xml.etree.ElementTree as E
from vi_structured import StructuredGraph,expr_value
from vi_design import tree
from vi_gui import INTERNAL
from state_layout import state_layout

class EngineeringGraph(StructuredGraph):
 def compile(self,n):
  key=(self.parent,ast.dump(n),tuple(sorted(self.env.items())))
  if not hasattr(self,'memo'):self.memo={}
  if key not in self.memo:self.memo[key]=super().compile(n)
  return self.memo[key]

 def case(self,selector,frames,depth,labels=None):
  # Carry only variables actually read or written inside the branch.
  needed=set()
  def scan(value):
   if isinstance(value,dict):
    if value.get('op')=='set':needed.add(value['name'])
    for key,v in value.items():
     if key in ('expression','condition','selector','array','count') and isinstance(v,str):
      needed.update(n.id for n in ast.walk(tree(v)) if isinstance(n,ast.Name))
     elif isinstance(v,(dict,list)):scan(v)
   elif isinstance(value,list):
    for v in value:scan(v)
  for label,body in frames:scan(body)
  outer=dict(self.env);self.env={k:v for k,v in outer.items() if k in needed}
  super().case(selector,frames,depth,labels)
  changed=self.env;self.env=outer;self.env.update(changed)

def cluster(fields):return 'cluster{'+','.join(t+'.'+n for n,t in fields)+'}'
def default(t):return [] if t.startswith('array{') else False if t=='bool' else 0

def compile_project(s,namespace=""):
 token=hashlib.sha256((json.dumps(s,sort_keys=True)+namespace).encode()).hexdigest()[:8]
 layout=state_layout(s);states=layout['flat']
 params=[(v['name'],v['type']) for v in s['inputs']]
 diagnostics=[(n,t) for n,t in INTERNAL.items() if n!='NI_Ready']
 st=layout['type'];pt,dt=map(cluster,(params,diagnostics));modules={}
 def graph(name,desc):return EngineeringGraph({'name':name,'description':desc,'variables':s['variables']})
 def terminal(g,tag,name,t,net=None,index=None,value=None):
  a={'_name':name,'type':t,'value':json.dumps(default(t) if value is None else value,separators=(',',':'))}
  if index is not None:a['conIdx']=str(index)
  if net is not None:a['inputs']='value:'+net
  e,u=g.element(tag,a)
  if tag=='Control':e.set('outputs','value:'+u+'.v')
  return u+'.v',t
 def unpack(g,net,fields):
  names={n:layout['paths'][n] if fields is states else n for n,t in fields}
  out=g.multi('Unbundle By Name',[('input cluster',net)],list(names.values()),{'fields':','.join(names.values())})
  return {n:(out[names[n]],t) for n,t in fields}
 def pack(g,fields,values,base=None):
  # Bundle with a typed input cluster so labels and field types remain explicit.
  typ=st if fields is states else cluster(fields);names={n:layout['paths'][n] if fields is states else n for n,t in fields}
  if base is None:base=g.constant(layout['defaults'] if fields is states else [default(t) for n,t in fields],typ)[0]
  out=g.multi('Bundle By Name',[('input cluster',base)]+[(names[n],values[n][0]) for n,t in fields],['output cluster'],{'fields':','.join(names.values())})
  return out['output cluster'],typ
 def finish(name,g):
  xml=E.tostring(g.root,encoding='unicode')+'\n<?lvmcp pane="4833"?>';modules[name+'.vi']=xml;return name+'.vi'
 def call(g,target,inputs,outputs):
  e,u=g.element('Call',{'target':target,'inputs':','.join(n+':'+v[0] for n,v in inputs),'outputs':''})
  result={n:(u+'.o'+str(i),t) for i,(n,t) in enumerate(outputs)};e.set('outputs',','.join(n+':'+v[0] for n,v in result.items()));return result
 # Command handler has one explicit state contract rather than many individual ports.
 name='HandleCommand_'+token;g=graph(name,'Apply a user command to application state. Pure dataflow; no GUI or hardware access.')
 state=terminal(g,'Control','StateIn',st,index=0,value=layout['initial']);p=terminal(g,'Control','Parameters',pt,index=1,value=[v['default'] for v in s['inputs']]);cmd=terminal(g,'Control','Command', 'int32',index=2);pressed=terminal(g,'Control','Pressed','bool',index=3)
 g.env.update(unpack(g,state[0],states));g.env.update(unpack(g,p[0],params))
 # Nested statement case reuses the restricted, validated IR compiler.
 body=[{'op':'state_machine','selector':'CommandCode','states':[{'value':i+1,'body':b['body']} for i,b in enumerate(s['buttons'])],'default':[]}]
 # use g.case directly because command selectors are typed backend data
 g.env['CommandCode']=cmd
 original=g.statements
 def commands(items,depth=0):
  if items is body:g.case(g.env['CommandCode'],[(str(i+1),b['body']) for i,b in enumerate(s['buttons'])]+[('Default',[])],depth)
  else:original(items,depth)
 g.statements=commands;g.case(pressed,[('True',body),('False',[])],0);g.statements=original
 result=pack(g,states,g.env,state[0]);terminal(g,'Indicator','StateOut',st,result[0],4,value=layout['defaults']);command=finish(name,g)
 name='ProcessTimeout_'+token;g=graph(name,'Process one timer tick. Owns sample processing and completion rules; deterministic and testable independently.')
 state=terminal(g,'Control','StateIn',st,index=0,value=layout['initial']);p=terminal(g,'Control','Parameters',pt,index=1,value=[v['default'] for v in s['inputs']]);g.env.update(unpack(g,state[0],states));g.env.update(unpack(g,p[0],params));g.statements(s['timeout']['body']);result=pack(g,states,g.env,state[0]);terminal(g,'Indicator','StateOut',st,result[0],4,value=layout['defaults']);timeout=finish(name,g)
 # Diagnostics deliberately separate from business state and timeout algorithm.
 name='UpdateDiagnostics_'+token;g=graph(name,'Update bounded execution diagnostics. Command code zero denotes an actual Timeout event.')
 diag=terminal(g,'Control','DiagnosticsIn',dt,index=0,value=[default(t) for n,t in diagnostics]);cmd=terminal(g,'Control','EventCode','int32',index=1);g.env.update(unpack(g,diag[0],diagnostics));g.env['EventCode']=cmd
 tick=[{'op':'set','name':'NI_TimeoutCount','expression':'NI_TimeoutCount+1'}]
 button=[{'op':'set','name':'NI_GuiEventCount','expression':'NI_GuiEventCount+1'},{'op':'set','name':'NI_GuiTrace','expression':'append(NI_GuiTrace,EventCode)'}]
 g.writable.update(n for n,t in diagnostics);g.case(g.compile(tree('EventCode == 0')),[('True',tick),('False',button)],0)
 # capture clock only on Timeout; generic statement compiler has no arbitrary NI calls.
 before=g.env['NI_TimeoutTimes'];clock=g.node('Tick Count (ms)',[],'millisecond timer value','int32');clock=g.coerce(clock,'double');start=g.compile(tree('int32(max(len(NI_TimeoutTimes)-63,0))'));recent=g.node('Array Subset',[('array',before),('index',start),('length',g.constant(63,'int32'))],'subarray','array{double}');single=g.node('Build Array',[('element',clock)],'appended array','array{double}');joined=g.multi('Build Array',[('array',recent[0]),('array',single[0])],['appended array'],{'concat':'true'});sel=g.compile(tree('EventCode == 0'));g.env['NI_TimeoutTimes']=g.node('Select',[('s',sel),('t',(joined['appended array'],'array{double}')),('f',before)],'s? t:f','array{double}')
 result=pack(g,diagnostics,g.env,diag[0]);terminal(g,'Indicator','DiagnosticsOut',dt,result[0],4,value=[default(t) for n,t in diagnostics]);diagnostic=finish(name,g)
 name='NormalizeTimeout_'+token;g=graph(name,'Clamp the configured timeout to 20..2000ms. Dedicated timing boundary.')
 p=terminal(g,'Control','Parameters',pt,index=0,value=[v['default'] for v in s['inputs']]);g.env.update(unpack(g,p[0],params));val=g.compile(tree('int32(clamp('+s['timeout']['interval']+',20,2000))'));terminal(g,'Indicator','TimeoutMs','int32',val[0],4);normalize=finish(name,g)
 name='EvaluateDisplay_'+token;g=graph(name,'Derive user display values and exit condition from application state. No mutation.')
 state=terminal(g,'Control','StateIn',st,index=0,value=layout['defaults']);p=terminal(g,'Control','Parameters',pt,index=1,value=[v['default'] for v in s['inputs']]);g.env.update(unpack(g,state[0],states));g.env.update(unpack(g,p[0],params));display_types=[]
 for i,c in enumerate(s['outputs']):
  val=g.compile(tree(c['expression']));display_types.append((c['name'],val[1]));terminal(g,'Indicator',c['name'],val[1],val[0],4+i)
 val=g.compile(tree(s['exit_condition']));terminal(g,'Indicator','ExitRequested','bool',val[0],10);display=finish(name,g)
 views=[(c['name'],c['type']) for c in s['inputs'] if c['type'].startswith('array{')]+[(n,t) for n,t in display_types if t.startswith('array{')]
 name='ConfigurePanel_'+token;g=graph(name,'Configure native array views once, before entering the event loop. Propagate initialization success.')
 err=None
 for i,(view,view_type) in enumerate(views):
  ref=terminal(g,'Control','View'+str(i+1),'ref{LV.Array}{'+view_type+'}',index=i)
  result=g.multi('Property Node',[('reference',ref[0]),('error in (no error)',err or ''),('Number of Rows',g.constant(8,'int32')[0]),('Number of Columns',g.constant(1,'int32')[0])],['reference out','error out'],{'type':'{LV.Array}','fields':'write+Number of Rows,write+Number of Columns'});err=result['error out']
 if err:
  status=g.multi('Unbundle By Name',[('input cluster',err)],['status'],{'fields':'status'})['status'];ok=g.node('Not',[('x',(status,'bool'))],'.not. x?','bool')
 else:ok=g.constant(True,'bool')
 terminal(g,'Indicator','Configured','bool',ok[0],15);configure=finish(name,g)
 # Main: two state rails, config bundle, Event Structure, and live display.
 g=graph(s['name'],s['description']+' Engineering layout: explicit application-state and diagnostics clusters, separate command/timer subVIs.')
 view_inputs=[]
 for i,(view,view_type) in enumerate(views):
  net=g.multi('VI Server Reference',[],[view],{'element':view})[view];view_inputs.append(('View'+str(i+1),(net,'ref{LV.Array}{'+view_type+'}')))
 configured=call(g,configure,view_inputs,[('Configured','bool')])['Configured']
 initial=g.constant(layout['initial'],st,'ApplicationStateSeed');initialdiag=g.constant([default(t) for n,t in diagnostics],dt,'DiagnosticsStateSeed')
 loop,lu=g.element('Structure',{'_name':'While Loop','count':'','label':'Application event loop | state + diagnostics'})
 with g.scope(loop,lu,{}):
  rights={}
  for key,seed in [('State',initial),('Diagnostics',initialdiag)]:
   sr,su=g.element('ShiftReg',{})
   with g.scope(sr,su,{}):
    l,li=g.element('Left',{'inputs':'value:'+seed[0],'outputs':''});l.set('outputs','value:'+li+'.v');r,ri=g.element('Right',{'inputs':'value:','outputs':''});r.set('outputs','value:'+ri+'.v')
   g.env[key]=(li+'.v',seed[1]);rights[key]=r
  for c in s['inputs']:g.env[c['name']]=terminal(g,'Control',c['name'],c['type'],index=s['connector'][c['name']],value=c['default'])
  configuration=pack(g,params,g.env);interval=call(g,normalize,[('Parameters',configuration)],[('TimeoutMs','int32')])['TimeoutMs']
  init,iu=g.tunnel('InitializationReady',configured[0]);init.set('outputs','value:'+iu+'.v');ready=(iu+'.v','bool');terminal(g,'Indicator','NI_Ready','bool',ready[0])
  outer={'State':g.env['State'],'Parameters':configuration,'Diagnostics':g.env['Diagnostics']}
  event,eu=g.element('Structure',{'_name':'Event Structure','timeout':interval[0]})
  with g.scope(event,eu,{}):
   for i,(key,val) in enumerate(outer.items()):g.tunnel('In'+str(i),val[0])
   for code,button in [(0,None)]+[(i+1,b['name']) for i,b in enumerate(s['buttons'])]:
    f,fu=g.element('CaseFrame',{'selector':' Timeout ' if button is None else ' "'+button+'"\\3A Value Change ','label':button or 'Process one sample'})
    with g.scope(f,fu,{}):
     for i,(key,val) in enumerate(outer.items()):
      t,tu=g.tunnel('In'+str(i));t.set('outputs','value:'+tu+'.v');g.env[key]=(tu+'.v',val[1])
     if button:
      terminal(g,'Control',button,'bool');data=g.multi('Event Data Node',[],['NewVal'],{'fields':'NewVal'});state=call(g,command,[('StateIn',g.env['State']),('Parameters',g.env['Parameters']),('Command',g.constant(code,'int32')),('Pressed',(data['NewVal'],'bool'))],[('StateOut',st)])['StateOut'];g.multi('Property Node',[('reference',''),('error in (no error)',''),('Value',g.constant(False,'bool')[0])],['reference out','error out'],{'type':'{LV.Boolean}','link':button,'fields':'write+Value'})
     else:state=call(g,timeout,[('StateIn',g.env['State']),('Parameters',g.env['Parameters'])],[('StateOut',st)])['StateOut']
     diag=call(g,diagnostic,[('DiagnosticsIn',g.env['Diagnostics']),('EventCode',g.constant(code,'int32'))],[('DiagnosticsOut',dt)])['DiagnosticsOut']
     g.tunnel('OutState',state[0]);g.tunnel('OutDiagnostics',diag[0])
   results={}
   for key,t in [('State',st),('Diagnostics',dt)]:
    e,u=g.tunnel('Out'+key);e.set('outputs','value:'+u+'.v');results[key]=(u+'.v',t)
  for key,r in rights.items():r.set('inputs','value:'+results[key][0])
  g.env.update(unpack(g,results['Diagnostics'][0],diagnostics))
  rendered=call(g,display,[('StateIn',results['State']),('Parameters',configuration)],display_types+[('ExitRequested','bool')])
  init_failed=g.node('Not',[('x',ready)],'.not. x?','bool');done=g.node('Or',[('x',rendered['ExitRequested']),('y',init_failed)],'x .or. y?','bool');g.element('Condition',{'inputs':'value:'+done[0],'value':'stop'})
  for c in s['outputs']:
   val=rendered[c['name']];terminal(g,'Indicator',c['name'],val[1],val[0],s['connector'][c['name']])
  for n,t in diagnostics:terminal(g,'Indicator',n,t,g.env[n][0])
 return E.tostring(g.root,encoding='unicode')+'\n<?lvmcp pane="4833"?>\n<?lvmcp engineering="true"?>',modules
