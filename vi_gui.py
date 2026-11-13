"""Live GUI event VI: static Boolean Value Change handlers plus a wired Timeout.
Uses the same typed statement compiler; tests are driven externally through Value(Signaling).
"""
import ast,copy,json,math,xml.etree.ElementTree as ET
from vi_design import DesignError,NAME,tree
from vi_structured import StructuredGraph,value_check,written,interpret,expr_value,RESERVED
INTERNAL={'NI_GuiEventCount':'int32','NI_TimeoutCount':'int32','NI_GuiTrace':'array{int32}','NI_TimeoutTimes':'array{double}','NI_Ready':'bool'}
def gui_compile(s):
 g=StructuredGraph(s);types={};controls={}
 portnames=[c['name'] for c in s['inputs']+s['outputs']]
 for c in s['inputs']:
  e,u=g.element('Control',{'_name':c['name'],'type':c['type'],'value':json.dumps(c['default'],separators=(',',':')),'outputs':''});e.set('outputs','value:'+u+'.v')
  if s['connector'][c['name']] is not None:e.set('conIdx',str(s['connector'][c['name']]))
  g.env[c['name']]=(u+'.v',c['type']);controls[c['name']]=(e,u);types[c['name']]=c['type']
 for v in s['variables']:g.env[v['name']]=g.expected(v['initial'],v['type']);types[v['name']]=v['type']
 # All GUI input terminals live in the loop. Initial shift-register seeds must be constants.
 state={k:v for k,v in g.env.items() if k not in controls}
 state.update({'NI_GuiEventCount':g.constant(0,'int32'),'NI_TimeoutCount':g.constant(0,'int32'),'NI_GuiTrace':g.constant([],'array{int32}'),'NI_TimeoutTimes':g.constant([],'array{double}')})
 changed=written(s['timeout']['body'])|set().union(*(written(b['body']) for b in s['buttons']))
 if not changed<=set(state):raise DesignError('GUI处理程序只能赋值已声明变量')
 allchanged=changed|{'NI_GuiEventCount','NI_TimeoutCount','NI_GuiTrace','NI_TimeoutTimes'};rights={};finals={}
 loop,lu=g.element('Structure',{'_name':'While Loop','count':'','label':'GUI event loop'})
 output_types={}
 with g.scope(loop,lu,{}):
  for i,(name,(net,typ)) in enumerate(state.items()):
   if name in allchanged:
    sr,su=g.element('ShiftReg',{})
    with g.scope(sr,su,{}):
     left,leftid=g.element('Left',{'inputs':'value:'+net,'outputs':''});left.set('outputs','value:'+leftid+'.v')
     right,rightid=g.element('Right',{'inputs':'value:','outputs':''});right.set('outputs','value:'+rightid+'.v')
    g.env[name]=(leftid+'.v',typ);rights[name]=right;finals[name]=(rightid+'.v',typ)
   else:
    t,tu=g.tunnel('In'+str(i+1),net);t.set('outputs','value:'+tu+'.v');g.env[name]=(tu+'.v',typ)
  for name,(e,u) in controls.items():g.root.remove(e);loop.append(e);e.set('uid_parent',lu);g.env[name]=(u+'.v',types[name])
  ready=g.constant(True,'bool');g.element('Indicator',{'_name':'NI_Ready','type':'bool','value':'false','inputs':'value:'+ready[0]})
  interval=g.compile(tree('int32(clamp('+s['timeout']['interval']+',20,2000))'))
  before=dict(g.env);event,eu=g.element('Structure',{'_name':'Event Structure','timeout':interval[0]})
  with g.scope(event,eu,{}):
   for i,(name,(net,typ)) in enumerate(before.items()):g.tunnel('In'+str(i+1),net)
   frames=[(' Timeout ',s['timeout']['body'],None)]+[(' "'+b['name']+'"\\3A Value Change ',b['body'],b['name']) for b in s['buttons']]
   for frame_index,(selector,body,button) in enumerate(frames):
    frame,fu=g.element('CaseFrame',{'selector':selector,'label':button or 'Timed update'})
    with g.scope(frame,fu,{}):
     for i,(name,(_,typ)) in enumerate(before.items()):
      t,tu=g.tunnel('In'+str(i+1));t.set('outputs','value:'+tu+'.v');g.env[name]=(tu+'.v',typ)
     if button:
      g.element('Control',{'_name':button,'type':'bool','value':'false','outputs':'','description':'Momentary GUI command; reset without signaling after handling.'})
      data=g.multi('Event Data Node',[],['NewVal'],{'fields':'NewVal'})
      g.case((data['NewVal'],'bool'),[('True',body),('False',[])],0)
      g.env['NI_GuiEventCount']=g.node('Add',[('x',g.env['NI_GuiEventCount']),('y',g.constant(1,'int32'))],'x+y','int32')
      # Readable trace uses 1..N for buttons and 0 for Timeout.
      code=g.constant(frame_index,'int32');single=g.node('Build Array',[('element',code)],'appended array','array{int32}')
      trace=g.multi('Build Array',[('array',g.env['NI_GuiTrace'][0]),('array',single[0])],['appended array'],{'concat':'true'});g.env['NI_GuiTrace']=(trace['appended array'],'array{int32}')
      false=g.constant(False,'bool')
      g.multi('Property Node',[('reference',''),('error in (no error)',''),('Value',false[0])],['reference out','error out'],{'type':'{LV.Boolean}','link':button,'fields':'write+Value'})
     else:
      g.statements(body)
      g.env['NI_TimeoutCount']=g.node('Add',[('x',g.env['NI_TimeoutCount']),('y',g.constant(1,'int32'))],'x+y','int32')
      raw_clock=g.node('Tick Count (ms)',[],'millisecond timer value','int32')
      clock=g.node('To Double Precision Float',[('number',raw_clock)],'double precision float','double')
      start=g.compile(tree('int32(max(len(NI_TimeoutTimes)-63,0))'))
      recent=g.node('Array Subset',[('array',g.env['NI_TimeoutTimes']),('index',start),('length',g.constant(63,'int32'))],'subarray','array{double}')
      single=g.node('Build Array',[('element',clock)],'appended array','array{double}')
      history=g.multi('Build Array',[('array',recent[0]),('array',single[0])],['appended array'],{'concat':'true'});g.env['NI_TimeoutTimes']=(history['appended array'],'array{double}')
     for i,name in enumerate(sorted(allchanged)):g.tunnel('Out'+str(i+1),g.coerce(g.env[name],before[name][1])[0])
   event_result={}
   for i,name in enumerate(sorted(allchanged)):
    t,tu=g.tunnel('Out'+str(i+1));t.set('outputs','value:'+tu+'.v');event_result[name]=(tu+'.v',before[name][1])
  g.env.update(event_result)
  for name,right in rights.items():right.set('inputs','value:'+g.env[name][0])
  done=g.compile(tree(s['exit_condition']))
  if done[1]!='bool':raise DesignError('GUI退出条件须为Boolean')
  g.element('Condition',{'inputs':'value:'+done[0],'value':'stop'})
  # Indicators are IN the loop, so the live front panel updates before termination.
  for c in s['outputs']:
   net,typ=g.compile(tree(c['expression']));output_types[c['name']]=typ
   attrs={'_name':c['name'],'type':typ,'value':'[]' if typ.startswith('array{') else 'false' if typ=='bool' else '0','inputs':'value:'+net}
   if s['connector'][c['name']] is not None:attrs['conIdx']=str(s['connector'][c['name']])
   g.element('Indicator',attrs)
  for name in ('NI_GuiEventCount','NI_TimeoutCount','NI_GuiTrace','NI_TimeoutTimes'):
   net,typ=g.env[name];g.element('Indicator',{'_name':name,'type':typ,'value':'[]' if typ.startswith('array{') else '0','inputs':'value:'+net})
 return ET.tostring(g.root,encoding='unicode')+'\n<?lvmcp pane="'+str(s['connector_pattern'])+'"?>',output_types

def validate_gui(spec):
 s=copy.deepcopy(spec)
 s.setdefault('engineering',True)
 s.setdefault('shared_typedefs',s['engineering'])
 if type(s['shared_typedefs']) is not bool or (s['shared_typedefs'] and not s['engineering']):raise DesignError('共享typedef需要启用工程模式并使用Boolean配置')
 if type(s['engineering']) is not bool:raise DesignError('工程模式须为Boolean')
 allowed={'state_groups','shared_typedefs','engineering','kind','name','description','inputs','variables','buttons','timeout','exit_condition','outputs','tests','assumptions','connector','connector_pattern'}
 if set(s)-allowed or len(json.dumps(s))>55000:raise DesignError('GUI设计字段或大小无效')
 if not isinstance(s.get('name'),str) or not NAME.fullmatch(s['name']):raise DesignError('VI名称无效')
 if not isinstance(s.get('description'),str) or not 1<=len(s['description'])<=2000:raise DesignError('描述无效')
 for key,lo,hi in [('inputs',1,6),('variables',1,20),('buttons',3,6),('outputs',1,6),('tests',1,3)]:
  if not isinstance(s.get(key),list) or not lo<=len(s[key])<=hi:raise DesignError(key+'数量无效')
 names=set();types={}
 def claim(name):
  if not isinstance(name,str) or not NAME.fullmatch(name) or name in names|RESERVED or name.startswith('NI_'):raise DesignError('名称无效或重复：'+str(name))
  names.add(name)
 for c in s['inputs']:
  if set(c)!={'name','type','default'}:raise DesignError('输入字段无效')
  claim(c['name']);value_check(c['default'],c['type']);types[c['name']]=c['type']
 for v in s['variables']:
  if set(v)!={'name','type','initial'}:raise DesignError('变量字段无效')
  claim(v['name']);types[v['name']]=v['type']
  if any(isinstance(n,ast.Name) for n in ast.walk(tree(v['initial']))):raise DesignError('GUI变量初始化须为常量，不可依赖运行中输入')
 from state_layout import state_layout
 state_layout(s)
 for b in s['buttons']:
  if set(b)!={'name','body'}:raise DesignError('按钮字段无效')
  claim(b['name'])
 for o in s['outputs']:
  if set(o)!={'name','expression'}:raise DesignError('输出字段无效')
  claim(o['name'])
 ports=[c['name'] for c in s['inputs']+s['outputs']];s.setdefault('connector',{n:i for i,n in enumerate(ports)});s.setdefault('connector_pattern',4833);s.setdefault('assumptions',[])
 slots=[n for n in s['connector'].values() if n is not None]
 if set(s['connector'])!=set(ports) or len(set(slots))!=len(slots) or any(type(x) is not int or not 0<=x<12 for x in slots):raise DesignError('连接器映射无效')
 if s['connector_pattern']!=4833:raise DesignError('GUI当前使用4833连接器')
 if set(s['timeout'])!={'interval','body'}:raise DesignError('Timeout字段无效')
 xml,outtypes=gui_compile(s);tests=[]
 def outputs(env):return {o['name']:value_check(expr_value(o['expression'],env),outtypes[o['name']]) for o in s['outputs']}
 def eq(a,b):
  if isinstance(b,list):return isinstance(a,list) and len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b))
  if type(b) is bool:return type(a) is bool and a==b
  return type(a) in (int,float) and math.isfinite(a) and abs(a-b)<=1e-8*max(1,abs(b))
 for case in s['tests']:
  if not isinstance(case.get('inputs'),dict) or set(case['inputs'])!={c['name'] for c in s['inputs']}:raise DesignError('GUI测试输入不完整')
  env={c['name']:copy.deepcopy(value_check(case['inputs'][c['name']],c['type'])) for c in s['inputs']}
  for v in s['variables']:env[v['name']]=value_check(expr_value(v['initial'],env),v['type'])
  interval=expr_value(s['timeout']['interval'],env)
  if type(interval) is not int or not 20<=interval<=2000:raise DesignError('Timeout间隔须为20至2000ms的int32')
  actions=case.get('actions');budget=[20000];buttons={b['name']:b['body'] for b in s['buttons']}
  if not isinstance(actions,list) or not 1<=len(actions)<=20:raise DesignError('GUI测试需要1至20个动作')
  exited=False
  for action in actions:
   if exited:raise DesignError('退出之后不能再发送GUI动作')
   if set(action)=={'event'} and action['event'] in buttons:interpret(buttons[action['event']],env,types,budget)
   elif set(action)=={'wait'}:
    if not isinstance(action['wait'],dict) or not action['wait']:raise DesignError('wait须给出目标输出')
    for _ in range(256):
     actual=outputs(env)
     if all(k in actual and (actual[k]>=v if type(v) in (int,float) else eq(actual[k],v)) for k,v in action['wait'].items()):break
     interpret(s['timeout']['body'],env,types,budget)
    else:raise DesignError('GUI等待条件无法通过Timeout到达')
   elif set(action)=={'stable','ticks'}:
    if type(action['ticks']) is not int or not 1<=action['ticks']<=4:raise DesignError('stable ticks须1至4')
    before=outputs(env)
    for _ in range(action['ticks']):interpret(s['timeout']['body'],env,types,budget)
    after=outputs(env)
    if any(k not in before or not eq(after[k],before[k]) for k in action['stable']):raise DesignError('所要求的暂停稳定性不成立')
   elif set(action)=={'expect'}:
    actual=outputs(env)
    if any(k not in actual or not eq(actual[k],v) for k,v in action['expect'].items()):raise DesignError('GUI中间断言与逻辑不一致')
   else:raise DesignError('未知GUI动作')
   exited=bool(expr_value(s['exit_condition'],env))
  if not exited:raise DesignError('GUI自动化测试必须通过按钮正常退出')
  expected=outputs(env)
  if case.get('expected') is not None and (set(case['expected'])!=set(expected) or not all(eq(case['expected'][k],v) for k,v in expected.items())):raise DesignError('GUI预期结果与独立解释器不一致')
  tests.append({'inputs':case['inputs'],'actions':actions,'expected':expected})
 s['tests']=tests;return s,xml,outtypes

GUI_SCHEMA='''
For real GUI Boolean button events and timed Timeout use kind="gui" (NOT a structured events command stream).
Schema: {"kind":"gui","name":"AsciiName","description":"purpose","inputs":[{"name":"Samples","type":"array{double}","default":[1.0,2.0,3.0]},{"name":"IntervalMs","type":"int32","default":100}],"variables":[{"name":"RunningValue","type":"bool","initial":"False"},{"name":"QuitValue","type":"bool","initial":"False"},{"name":"Buffer","type":"array{double}","initial":"[]"},{"name":"Index","type":"int32","initial":"0"}],"buttons":[{"name":"Start","body":[STATEMENTS]},{"name":"Stop","body":[STATEMENTS]},{"name":"Reset","body":[STATEMENTS]},{"name":"Exit","body":[{"op":"set","name":"QuitValue","expression":"True"}]}],"timeout":{"interval":"IntervalMs","body":[STATEMENTS]},"exit_condition":"QuitValue","outputs":[{"name":"Values","expression":"Buffer"},{"name":"TickCount","expression":"Index"},{"name":"Running","expression":"RunningValue"}],"tests":[{"inputs":{"Samples":[1.0,2.0,3.0],"IntervalMs":100},"actions":[{"event":"Start"},{"wait":{"TickCount":1}},{"event":"Stop"},{"stable":["TickCount","Values"],"ticks":2},{"event":"Reset"},{"expect":{"TickCount":0,"Running":false}},{"event":"Start"},{"wait":{"TickCount":3,"Running":false}},{"event":"Exit"}],"expected":{"Values":[1.0,2.0,3.0],"TickCount":3,"Running":false}}],"assumptions":[]}
The variables/expressions/statement bodies follow structured language, but variables initialize with CONSTANTS only. Buttons are real switch-action pushbuttons with Value Change frames and automatic non-signaling reset to false; Value(Signaling) externally triggers actual events. Button names Start/Stop/Reset/Exit preferred; 3..6 buttons. Stop should PAUSE without exit, Exit terminates. Exit must also set Running false. Timeout is physically wired and configurable20..2000ms, inputs are read live in the loop. Indicators update on each event. No model code or arbitrary NI properties.
Connector preservation is PROVIDED by the backend: optional fields connector={"InputName":0,"OutputName":3} and connector_pattern=4833 are supported. For edits the backend automatically preserves all existing named port slots and assigns added ports to free slots. Do not refuse a request to preserve connectors; no scripting is required from the model. You can omit these two fields from your output. Only 1..3 tests, each<=20 actions. For deterministic tests, process a finite input array: Timeout advances one sample while Running, automatically sets Running false at end. Start after end can reset and start anew. Stop pauses; Reset stops and clears Buffer/Index; Exit ends UI. Reuse general set/if/for_each/state_machine statements in bodies. 6 outputs max, all output names DIFFER from variable names. Max24 variables. GUI tests use event,wait,stable+ticks,expect actions exactly as shown; numeric wait targets are LOWER BOUNDS (>=), Boolean/array targets exact. Stop may occur after more than one tick due to asynchronous scheduling: do NOT assert an exact in-flight tick count; use stable checks then Reset for a deterministic final run; wait targets output values, stable checks observed actual outputs remain unchanged while real timeouts continue. Always include Exit as last action. Include startup/stop stability/reset/restart and empty array cases. Do NOT predict a fixed number of idle Timeout events or wallclock time. Event counts and timing diagnostics are added internally. Expected final outputs must be calculated independently.
'''

GUI_SCHEMA += """
Optional state_groups=[{"name":"Metrics","fields":["NextIndex","PeakAbsValue"]}] physically nests those existing variables in a separate shared Metrics.ctl inside ApplicationState.ctl. At most ONE group, existing variable names only, no duplicates; group name must not collide with variables/ApplicationState/DiagnosticsState. Business variable declarations, expressions and statements MUST KEEP using their FLAT names (NextIndex, PeakAbsValue); the backend maps to Metrics.NextIndex and Metrics.PeakAbsValue. Do not declare a cluster variable or use dotted expressions. Preserve existing groups unless requested to change/delete them. Type edits must update initial values and every assignment with explicit int32/double conversion as required. Deleting a variable must remove all reads/writes and relevant outputs/test assertions.
"""
