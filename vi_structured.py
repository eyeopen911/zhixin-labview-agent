"""Structured VI IR: bounded loops, array dataflow, case state machines and real user events."""
from __future__ import annotations
import ast,copy,json,math,xml.etree.ElementTree as ET
from contextlib import contextmanager
from vi_design import Graph,DesignError,NAME,BIN,CMP,FUN,tree,evaluate
TYPES={'double','bool','int32','array{double}','array{int32}'}
SENTINEL=-2147483648
RESERVED={'len','sum','mean','append','concat','int32','double','abs','sqrt','sin','cos','round','min','max','clamp','NI_RuntimeError','NI_RuntimeStatus'}
def value_check(v,t):
 if t.startswith('array{'):
  if not isinstance(v,list) or len(v)>2048:raise DesignError('数组须为列表，最多2048个元素')
  for x in v:value_check(x,t[6:-1])
 elif t=='bool':
  if type(v) is not bool:raise DesignError('需要Boolean值')
 elif t in ('int32','double'):
  if type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e12:raise DesignError('需要有限数值')
  if t=='int32' and (type(v) is not int or not -2147483647<=v<=2147483647):raise DesignError('int32数值无效；最小int32保留给内部停止事件')
 else:raise DesignError('类型不受支持：'+str(t))
 return v

def isnum(t):return t in ('double','int32')
def written(body):
 if not isinstance(body,list) or any(not isinstance(st,dict) for st in body):raise DesignError('程序须为语句对象列表')
 out=set()
 for st in body:
  if st.get('op')=='set':out.add(st['name'])
  for k in ('body','then','else','default'):
   if isinstance(st.get(k),list):out|=written(st[k])
  for state in st.get('states',[]):out|=written(state['body'])
  out|={c['name'] for c in st.get('collect',[])}
 return out

class StructuredGraph(Graph):
 def __init__(self,spec):
  super().__init__(spec);self.container=self.root;self.parent='root';self.event_count=0;self.writable={c['name'] for c in spec['variables']}
 def element(self,tag,attrs):
  self.uid+=1;attrs=dict(attrs,uid=str(self.uid),uid_parent=self.parent);e=ET.SubElement(self.container,tag,attrs);return e,str(self.uid)
 @contextmanager
 def scope(self,element,uid,env):
  old=self.container,self.parent,self.env;self.container,self.parent,self.env=element,uid,env
  try:yield
  finally:self.container,self.parent,self.env=old
 def node(self,name,args,out,typ):
  self.count+=1
  if self.count>500:raise DesignError('结构化VI原语超过500个')
  e,u=self.element('Node',{'_name':name,'inputs':','.join(k+':'+v[0] for k,v in args),'outputs':''});net=u+'.out';e.set('outputs',out+':'+net);return net,typ
 def multi(self,name,inputs,outputs,attrs=None):
  self.count+=1
  if self.count>500:raise DesignError('结构化VI节点超过500个')
  e,u=self.element('Node',dict(attrs or {},_name=name,inputs=','.join(k+':'+v for k,v in inputs),outputs=''))
  nets={key:u+'.o'+str(i) for i,key in enumerate(outputs)};e.set('outputs',','.join(key+':'+net for key,net in nets.items()));return nets
 def constant(self,v,t,label=None):
  attrs={'type':t,'value':json.dumps(v,separators=(',',':')),'outputs':''}
  if label:attrs['_name']=label
  e,u=self.element('Constant',attrs);e.set('outputs','value:'+u+'.value');return u+'.value',t
 def coerce(self,value,t):
  if value[1]==t:return value
  if value[1]=='int32' and t=='double':return self.node('To Double Precision Float',[('number',value)],'double precision float','double')
  # Empty array type is specified at the source by expected().
  raise DesignError('类型不匹配：'+value[1]+' -> '+t)
 def expected(self,expr,t):
  n=tree(expr)
  if isinstance(n,ast.List) and not n.elts and t.startswith('array{'):return self.constant([],t)
  return self.coerce(self.compile(n),t)
 def compile(self,n):
  if isinstance(n,ast.Constant):
   t='bool' if type(n.value) is bool else 'int32' if type(n.value) is int else 'double';value_check(n.value,t);return self.constant(n.value,t)
  if isinstance(n,ast.List):
   vals=[]
   for el in n.elts:
    if isinstance(el,ast.Constant) and type(el.value) in (int,float):vals.append(el.value)
    elif isinstance(el,ast.UnaryOp) and isinstance(el.op,ast.USub) and isinstance(el.operand,ast.Constant):vals.append(-el.operand.value)
    else:raise DesignError('数组字面量仅支持数值常量；动态元素用append')
   t='array{int32}' if vals and all(type(x) is int for x in vals) else 'array{double}';value_check(vals,t);return self.constant(vals,t)
  if isinstance(n,ast.BinOp) and type(n.op) in BIN:
   x,y=self.compile(n.left),self.compile(n.right)
   if not isnum(x[1]) or not isnum(y[1]):raise DesignError('数组逐元素计算请使用for_each循环')
   nm,out=BIN[type(n.op)];typ='double' if 'double' in (x[1],y[1]) or isinstance(n.op,ast.Div) else 'int32'
   return self.node(nm,[('x',x),('y',y)],out,typ)
  if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):
   x=self.compile(n.operand)
   if not isnum(x[1]):raise DesignError('负号要求数值')
   return x if isinstance(n.op,ast.UAdd) else self.node('Negate',[('x',x)],'-x',x[1])
  if isinstance(n,ast.Compare) and all(type(o) in CMP for o in n.ops):
   vals=[self.compile(v) for v in [n.left]+n.comparators];out=None
   for i,o in enumerate(n.ops):
    x,y=vals[i:i+2]
    if not (isnum(x[1]) and isnum(y[1])) and not (x[1]==y[1]=='bool' and type(o) in (ast.Eq,ast.NotEq)):raise DesignError('比较类型不兼容')
    nm,t=CMP[type(o)];v=self.node(nm,[('x',x),('y',y)],t,'bool');out=v if out is None else self.node('And',[('x',out),('y',v)],'x .and. y?','bool')
   return out
  if isinstance(n,ast.IfExp):
   s,t,f=self.compile(n.test),self.compile(n.body),self.compile(n.orelse)
   if s[1]!='bool':raise DesignError('条件须Boolean')
   if t[1]!=f[1] and isnum(t[1]) and isnum(f[1]):t,f=self.coerce(t,'double'),self.coerce(f,'double')
   if t[1]!=f[1]:raise DesignError('Select两端类型不一致')
   return self.node('Select',[('s',s),('t',t),('f',f)],'s? t:f',t[1])
  if isinstance(n,ast.Subscript):
   a,i=self.compile(n.value),self.compile(n.slice)
   if not a[1].startswith('array{') or i[1]!='int32':raise DesignError('索引须int32，源须数组')
   return self.node('Index Array',[('array',a),('index',i)],'element',a[1][6:-1])
  if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and not n.keywords:
   name=n.func.id
   if name in ('len','sum','mean') and len(n.args)==1:
    a=self.compile(n.args[0])
    if not a[1].startswith('array{'):raise DesignError(name+'要求数组')
    if name=='len':return self.node('Array Size',[('array',a)],'size(s)','int32')
    total=self.node('Add Array Elements',[('numeric array',a)],'sum',a[1][6:-1])
    if name=='sum':return total
    size=self.node('Array Size',[('array',a)],'size(s)','int32');one=self.constant(1,'int32');valid=self.node('Greater?',[('x',size),('y',one)],'x > y?','bool');denom=self.node('Select',[('s',valid),('t',size),('f',one)],'s? t:f','int32')
    return self.node('Divide',[('x',total),('y',denom)],'x/y','double')
   if name=='append' and len(n.args)==2:
    a,x=self.compile(n.args[0]),self.compile(n.args[1])
    if not a[1].startswith('array{'):raise DesignError('append第一个参数须数组')
    x=self.coerce(x,a[1][6:-1]);single=self.node('Build Array',[('element',x)],'appended array',a[1]);nets=self.multi('Build Array',[('array',a[0]),('array',single[0])],['appended array'],{'concat':'true'});return nets['appended array'],a[1]
   if name=='concat' and len(n.args)==2:
    a,b=self.compile(n.args[0]),self.compile(n.args[1])
    if not a[1].startswith('array{') or a[1]!=b[1]:raise DesignError('concat要求相同类型数组')
    nets=self.multi('Build Array',[('array',a[0]),('array',b[0])],['appended array'],{'concat':'true'});return nets['appended array'],a[1]
   if name in ('double','int32') and len(n.args)==1:
    x=self.compile(n.args[0])
    if not isnum(x[1]):raise DesignError('转换须数值')
    return self.node('To Double Precision Float' if name=='double' else 'To Long Integer',[('number',x)],'double precision float' if name=='double' else '32bit integer',name)
   if name in FUN and len(n.args)==1:
    x=self.compile(n.args[0])
    if not isnum(x[1]):raise DesignError('数学函数要求数值')
    nm,inp,out=FUN[name];typ=x[1] if name=='abs' else 'double'
    if name in ('sqrt','sin','cos','round'):x=self.coerce(x,'double')
    return self.node(nm,[(inp,x)],out,typ)
  return super().compile(n)
 def statements(self,body,depth=0):
  if depth>8 or not isinstance(body,list) or len(body)>60:raise DesignError('程序嵌套或语句数量超限')
  for st in body:
   if not isinstance(st,dict):raise DesignError('语句须为对象')
   op=st.get('op')
   allowed={'set':{'op','name','expression'},'if':{'op','condition','then','else'},'for_each':{'op','array','item','index','body','collect'},'for':{'op','count','index','body','collect'},'while':{'op','until','max_iterations','index','body'},'state_machine':{'op','state','states','default'},'events':{'op','commands','event','body'}}
   if op not in allowed or set(st)-allowed[op]:raise DesignError('未知语句或字段：'+str(op))
   if op=='set':
    if st.get('name') not in self.env or st.get('name') not in self.writable:raise DesignError('赋值目标须为已声明变量：'+str(st.get('name')))
    self.env[st['name']]=self.expected(st['expression'],self.env[st['name']][1])
   elif op=='if':
    cond=self.compile(tree(st['condition']))
    if cond[1]!='bool':raise DesignError('if条件须Boolean')
    self.case(cond,[('True',st['then']),('False',st.get('else',[]))],depth)
   elif op=='state_machine':
    state=self.compile(tree(st['state']))
    if state[1]!='int32':raise DesignError('状态编号须int32')
    states=st.get('states',[])
    if not isinstance(states,list) or not 1<=len(states)<=12:raise DesignError('状态数量须1至12')
    ids=[x.get('value') for x in states]
    if any(type(x) is not int or not 0<=x<=100 for x in ids) or len(set(ids))!=len(ids):raise DesignError('状态编号无效或重复')
    self.case(state,[(str(x['value']),x['body']) for x in states]+[('Default',st.get('default',[]))],depth,labels={str(x['value']):x.get('name','State'+str(x['value'])) for x in states})
   elif op in ('for','for_each','while'):self.loop(st,depth)
   elif op=='events':self.events(st,depth)
 def tunnel(self,tagid,net=None,out=False,mode=None):
  attrs={'_id':tagid}
  if net is not None:attrs['outputs' if out else 'inputs']='value:'+net
  if mode:attrs['mode']=mode
  e,u=self.element('Tunnel',attrs)
  return e,u
 def case(self,selector,frames,depth,labels=None):
  outer=dict(self.env);changes=set().union(*(written(b) for _,b in frames))
  if not changes<=set(outer):raise DesignError('分支赋值须先声明变量')
  e,u=self.element('Structure',{'_name':'Case Structure','selectin':selector[0]})
  inputs={name:'In'+str(i+1) for i,name in enumerate(outer)};outs={name:'Out'+str(i+1) for i,name in enumerate(sorted(changes))}
  with self.scope(e,u,{}):
   for name,tid in inputs.items():self.tunnel(tid,outer[name][0])
   for label,body in frames:
    f,fu=self.element('CaseFrame',{'selector':label,'selectout':'','label':(labels or {}).get(label,label)})
    with self.scope(f,fu,{}):
     for name,tid in inputs.items():
      t,tu=self.tunnel(tid);t.set('outputs','value:'+tu+'.v');self.env[name]=(tu+'.v',outer[name][1])
     self.statements(body,depth+1)
     for name,tid in outs.items():self.tunnel(tid,self.coerce(self.env[name],outer[name][1])[0])
   finals={}
   for name,tid in outs.items():
    t,tu=self.tunnel(tid);t.set('outputs','value:'+tu+'.v');finals[name]=(tu+'.v',outer[name][1])
  self.env.update(finals)
 def loop(self,st,depth):
  kind=st['op'];outer=dict(self.env);collect=st.get('collect',[])
  if not isinstance(collect,list) or len(collect)>4:raise DesignError('收集输出最多4个')
  collected={c['name'] for c in collect};changes=written(st['body'])-collected
  if not changes<=set(outer) or not collected<=set(outer):raise DesignError('循环结果须预先声明')
  if kind=='for_each':
   source=self.compile(tree(st['array']))
   if not source[1].startswith('array{'):raise DesignError('for_each需要数组')
   maxin=''
  elif kind=='for':
   count=self.compile(tree(st['count']))
   if count[1]!='int32':raise DesignError('for次数须int32')
   # Bound even variable counts inside the actual VI.
   count=self.compile(tree('int32(clamp('+st['count']+', 0, 1024))'));maxin=count[0]
  else:
   limit=st.get('max_iterations')
   if type(limit) is not int or not 1<=limit<=1024:raise DesignError('while需1至1024的最大次数')
   if collect:raise DesignError('while暂不支持自动收集，使用append与移位寄存器')
  attrs={'_name':'While Loop' if kind=='while' else 'For Loop','count':'','label':kind}
  if kind!='while':attrs.update(maxin=maxin,maxout='')
  e,u=self.element('Structure',attrs);e.set('count',u+'.i');finals={};rights={}
  with self.scope(e,u,{}):
   for i,(name,(net,typ)) in enumerate(outer.items()):
    if name in collected:continue
    if name in changes:
     sr,su=self.element('ShiftReg',{})
     with self.scope(sr,su,{}):
      l,lu=self.element('Left',{'inputs':'value:'+net,'outputs':''});l.set('outputs','value:'+lu+'.v')
      r,ru=self.element('Right',{'inputs':'value:','outputs':''});r.set('outputs','value:'+ru+'.v')
     self.env[name]=(lu+'.v',typ);rights[name]=r;finals[name]=(ru+'.v',typ)
    else:
     t,tu=self.tunnel('In'+str(i+1),net);t.set('outputs','value:'+tu+'.v');self.env[name]=(tu+'.v',typ)
   index=st.get('index','LoopIndex')
   if not isinstance(index,str) or not NAME.fullmatch(index) or index in outer:raise DesignError('循环index须为未占用标识符')
   self.env[index]=(u+'.i','int32')
   if kind=='for_each':
    item=st['item']
    if not NAME.fullmatch(item) or item in outer or item==index:raise DesignError('循环item名称无效')
    t,tu=self.tunnel('In'+str(len(outer)+1),source[0],mode='index');t.set('outputs','value:'+tu+'.v');self.env[item]=(tu+'.v',source[1][6:-1])
   self.statements(st['body'],depth+1)
   for name,r in rights.items():r.set('inputs','value:'+self.coerce(self.env[name],outer[name][1])[0])
   for i,c in enumerate(collect):
    typ=outer[c['name']][1]
    if not typ.startswith('array{'):raise DesignError('collect目标须数组')
    value=self.expected(c['expression'],typ[6:-1]);t,tu=self.tunnel('Out'+str(i+1),value[0],mode='index');t.set('outputs','value:'+tu+'.v');finals[c['name']]=(tu+'.v',typ)
   if kind=='while':
    stop=self.compile(tree(st['until']))
    if stop[1]!='bool':raise DesignError('while终止条件须Boolean')
    cap=self.constant(st['max_iterations']-1,'int32');hit=self.node('Greater Or Equal?',[('x',(u+'.i','int32')),('y',cap)],'x >= y?','bool');end=self.node('Or',[('x',stop),('y',hit)],'x .or. y?','bool');self.element('Condition',{'inputs':'value:'+end[0],'value':'stop'})
  self.env.update(finals)
 def events(self,st,depth):
  if depth!=0 or self.event_count:raise DesignError('每个VI支持一个顶层User Event循环')
  self.event_count+=1;outer=dict(self.env);commands=self.compile(tree(st['commands']))
  if commands[1]!='array{int32}':raise DesignError('事件命令须array{int32}')
  eventname=st['event']
  if not isinstance(eventname,str) or not NAME.fullmatch(eventname) or eventname in outer:raise DesignError('事件变量名称无效或重复')
  changes=written(st['body'])
  if not changes<=set(outer):raise DesignError('事件处理结果须先声明变量')
  datatype=self.constant(0,'int32',eventname)
  created=self.multi('Create User Event',[('user event datatype',datatype[0]),('error in','')],['user event','error out'])
  reg=self.multi('Register For Events',[('event registration refnum',''),('error in (no error)',created['error out']),('event source',created['user event'])],['event registration refnum','error out'])
  # Append a reserved final event. It really traverses the same queue, and guarantees completion.
  final=self.constant([SENTINEL],'array{int32}')
  stream=self.multi('Build Array',[('array',commands[0]),('array',final[0])],['appended array'],{'concat':'true'})['appended array']
  producer,pu=self.element('Structure',{'_name':'For Loop','count':'','maxin':'','maxout':'','label':'User event producer'})
  with self.scope(producer,pu,{}):
   t,tu=self.tunnel('In1',stream,mode='index');t.set('outputs','value:'+tu+'.v');payload=tu+'.v'
   t,tu=self.tunnel('In2',created['user event']);t.set('outputs','value:'+tu+'.v');eventref=tu+'.v'
   sr,su=self.element('ShiftReg',{})
   with self.scope(sr,su,{}):
    l,lu=self.element('Left',{'inputs':'value:'+reg['error out'],'outputs':''});l.set('outputs','value:'+lu+'.v')
    r,ru=self.element('Right',{'inputs':'value:','outputs':''});r.set('outputs','value:'+ru+'.v')
   emitted=self.multi('Generate User Event',[('user event',eventref),('event data cluster',payload),('error in',lu+'.v'),('priority (normal)','')],['user event out','error out'])
   r.set('inputs','value:'+emitted['error out']);producer_error=ru+'.v'
  consumer,cu=self.element('Structure',{'_name':'While Loop','count':'','label':'Event-driven state machine'});rights={};finals={}
  with self.scope(consumer,cu,{}):
   for i,(name,(net,typ)) in enumerate(outer.items()):
    if name in changes:
     sr,su=self.element('ShiftReg',{})
     with self.scope(sr,su,{}):
      l,lu=self.element('Left',{'inputs':'value:'+net,'outputs':''});l.set('outputs','value:'+lu+'.v')
      r,ru=self.element('Right',{'inputs':'value:','outputs':''});r.set('outputs','value:'+ru+'.v')
     self.env[name]=(lu+'.v',typ);rights[name]=r;finals[name]=(ru+'.v',typ)
    else:
     t,tu=self.tunnel('In'+str(i+1),net);t.set('outputs','value:'+tu+'.v');self.env[name]=(tu+'.v',typ)
   t,tu=self.tunnel('In'+str(len(outer)+1),reg['event registration refnum']);t.set('outputs','value:'+tu+'.v');registration=tu+'.v'
   event_outer=dict(self.env);evt,eu=self.element('Structure',{'_name':'Event Structure'})
   with self.scope(evt,eu,{}):
    self.tunnel('In1',registration)
    for i,(name,(net,typ)) in enumerate(event_outer.items()):self.tunnel('In'+str(i+2),net)
    for event_selector,isuser in [(' <'+eventname+'>\\3A User Event ',True),(' Timeout ',False)]:
     f,fu=self.element('CaseFrame',{'selector':event_selector,'label':'Handle command' if isuser else 'Idle timeout'})
     with self.scope(f,fu,{}):
      self.tunnel('In1',out=True,net='')
      for i,(name,(_,typ)) in enumerate(event_outer.items()):
       t,tu=self.tunnel('In'+str(i+2));t.set('outputs','value:'+tu+'.v');self.env[name]=(tu+'.v',typ)
      if isuser:
       data=self.multi('Event Data Node',[],[eventname],{'fields':eventname});self.env[eventname]=(data[eventname],'int32')
       sentinel=self.constant(SENTINEL,'int32');stop=self.node('Equal?',[('x',self.env[eventname]),('y',sentinel)],'x = y?','bool')
       self.case(stop,[('True',[]),('False',st['body'])],depth+1)
      else:stop=self.constant(False,'bool')
      self.tunnel('Out1',stop[0])
      for i,name in enumerate(sorted(changes)):self.tunnel('Out'+str(i+2),self.coerce(self.env[name],outer[name][1])[0])
    t,tu=self.tunnel('Out1');t.set('outputs','value:'+tu+'.v');stopnet=tu+'.v';event_results={}
    for i,name in enumerate(sorted(changes)):
     t,tu=self.tunnel('Out'+str(i+2));t.set('outputs','value:'+tu+'.v');event_results[name]=(tu+'.v',outer[name][1])
   for name,r in rights.items():r.set('inputs','value:'+event_results[name][0])
   self.element('Condition',{'inputs':'value:'+stopnet,'value':'stop'})
   t,tu=self.tunnel('Out1',registration);t.set('outputs','value:'+tu+'.v');completed_reg=tu+'.v'
  self.env.update(finals)
  unreg=self.multi('Unregister For Events',[('event registration refnum',completed_reg),('error in',producer_error)],['error out'])
  destroyed=self.multi('Destroy User Event',[('user event',created['user event']),('error in',unreg['error out'])],['error out'])
  error=self.multi('Unbundle By Name',[('input cluster',destroyed['error out'])],['status','code'],{'fields':'status,code'})
  self.element('Indicator',{'_name':'NI_RuntimeError','type':'int32','value':'0','inputs':'value:'+error['code']})
  self.element('Indicator',{'_name':'NI_RuntimeStatus','type':'bool','value':'false','inputs':'value:'+error['status']})

def expr_value(expr,env):
 n=tree(expr)
 def walk(n):
  if isinstance(n,ast.Name):return env[n.id]
  if isinstance(n,ast.Constant):return n.value
  if isinstance(n,ast.List):return [walk(v) for v in n.elts]
  if isinstance(n,ast.Subscript):
   a,i=walk(n.value),walk(n.slice);return a[i] if 0<=i<len(a) else 0
  if isinstance(n,ast.Call):
   if not isinstance(n.func,ast.Name):raise DesignError('函数调用无效')
   args=[walk(v) for v in n.args];name=n.func.id
   funcs={'len':len,'sum':sum,'mean':lambda a:sum(a)/max(1,len(a)),'append':lambda a,x:a+[x],'concat':lambda a,b:a+b,'double':float,'int32':lambda x:int(round(x)),'abs':abs,'sqrt':math.sqrt,'sin':math.sin,'cos':math.cos,'round':round,'min':min,'max':max,'clamp':lambda x,lo,hi:min(max(x,lo),hi)}
   return funcs[name](*args)
  if isinstance(n,ast.BinOp):
   x,y=walk(n.left),walk(n.right)
   return {ast.Add:lambda:x+y,ast.Sub:lambda:x-y,ast.Mult:lambda:x*y,ast.Div:lambda:x/y,ast.Pow:lambda:x**y}[type(n.op)]()
  if isinstance(n,ast.UnaryOp):
   x=walk(n.operand);return {ast.UAdd:lambda:+x,ast.USub:lambda:-x,ast.Not:lambda:not x}[type(n.op)]()
  if isinstance(n,ast.Compare):
   vals=[walk(v) for v in [n.left]+n.comparators]
   for i,o in enumerate(n.ops):
    x,y=vals[i:i+2]
    if not {ast.Gt:lambda:x>y,ast.Lt:lambda:x<y,ast.GtE:lambda:x>=y,ast.LtE:lambda:x<=y,ast.Eq:lambda:x==y,ast.NotEq:lambda:x!=y}[type(o)]():return False
   return True
  if isinstance(n,ast.BoolOp):
   a=[walk(v) for v in n.values];return all(a) if isinstance(n.op,ast.And) else any(a)
  if isinstance(n,ast.IfExp):
   c,x,y=walk(n.test),walk(n.body),walk(n.orelse);return x if c else y
  raise DesignError('表达式不受支持')
 return walk(n)

def interpret(body,env,types,budget):
 for st in body:
  budget[0]-=1
  if budget[0]<0:raise DesignError('测试执行预算超过20000步')
  op=st['op']
  if op=='set':
   v=expr_value(st['expression'],env);value_check(v,types[st['name']]);env[st['name']]=v
  elif op=='if':interpret(st['then'] if expr_value(st['condition'],env) else st.get('else',[]),env,types,budget)
  elif op=='state_machine':
   state=expr_value(st['state'],env);selected=next((x['body'] for x in st['states'] if x['value']==state),st.get('default',[]));interpret(selected,env,types,budget)
  elif op in ('for','for_each','while'):
   if op=='for_each':values=list(expr_value(st['array'],env));count=len(values)
   elif op=='for':count=min(1024,max(0,expr_value(st['count'],env)))
   else:count=st['max_iterations']
   collected={c['name']:[] for c in st.get('collect',[])};local=copy.deepcopy(env)
   for i in range(count):
    local[st.get('index','LoopIndex')]=i
    if op=='for_each':local[st['item']]=values[i]
    interpret(st['body'],local,types,budget)
    for c in st.get('collect',[]):collected[c['name']].append(expr_value(c['expression'],local))
    if op=='while' and expr_value(st['until'],local):break
   for k in written(st['body'])-set(collected):env[k]=local[k]
   env.update(collected)
  elif op=='events':
   commands=expr_value(st['commands'],env)
   if len(commands)>64 or SENTINEL in commands:raise DesignError('事件命令最多64个，且不得包含内部停止标记')
   for command in commands:
    local=dict(env);local[st['event']]=command;interpret(st['body'],local,types,budget)
    for k in written(st['body']):env[k]=local[k]
  else:raise DesignError('未知语句')

def validate_structured(spec):
 s=copy.deepcopy(spec)
 if len(json.dumps(s,ensure_ascii=False))>55000:raise DesignError('结构化设计超过55KB')
 allowed={'kind','name','description','inputs','variables','program','outputs','tests','assumptions','connector','connector_pattern'}
 if set(s)-allowed:raise DesignError('结构化设计包含未知字段')
 if not isinstance(s.get('name'),str) or not NAME.fullmatch(s['name']):raise DesignError('VI名称无效')
 if not isinstance(s.get('description'),str) or not 1<=len(s['description'])<=2000:raise DesignError('VI描述无效')
 for key,minimum,maximum in [('inputs',1,6),('outputs',1,6),('variables',0,24)]:
  if not isinstance(s.get(key),list) or not minimum<=len(s[key])<=maximum:raise DesignError(key+'数量超限')
 s.setdefault('assumptions',[])
 if not isinstance(s['assumptions'],list) or any(not isinstance(x,str) or len(x)>500 for x in s['assumptions']):raise DesignError('设计假设无效')
 names=set();types={};g=StructuredGraph(s)
 def claim(name):
  if not isinstance(name,str) or not NAME.fullmatch(name) or name in names|RESERVED or name.startswith('NI_'):raise DesignError('名称无效、保留或重复：'+str(name))
  names.add(name)
 portnames=[c.get('name') for c in s['inputs']+s['outputs']];connector=s.get('connector',{n:i for i,n in enumerate(portnames)})
 if not isinstance(connector,dict) or set(connector)!=set(portnames):raise DesignError('连接器映射不完整')
 slots=[v for v in connector.values() if v is not None]
 if any(type(v) is not int or not 0<=v<12 for v in slots) or len(set(slots))!=len(slots):raise DesignError('连接器映射无效')
 s['connector']=connector;s.setdefault('connector_pattern',4833)
 if type(s['connector_pattern']) is not int or not 4800<=s['connector_pattern']<=4899:raise DesignError('连接器图案无效')
 for c in s['inputs']:
  if set(c)!={'name','type','default'}:raise DesignError('输入字段无效')
  claim(c['name']);value_check(c['default'],c['type']);types[c['name']]=c['type']
  e,u=g.element('Control',{'_name':c['name'],'type':c['type'],'value':json.dumps(c['default'],separators=(',',':')),'outputs':'','connection':'required'});e.set('outputs','value:'+u+'.value')
  if connector[c['name']] is not None:e.set('conIdx',str(connector[c['name']]))
  g.env[c['name']]=(u+'.value',c['type'])
 for c in s['variables']:
  if set(c)!={'name','type','initial'} or c['type'] not in TYPES:raise DesignError('变量字段或类型无效')
  claim(c['name']);types[c['name']]=c['type'];g.env[c['name']]=g.expected(c['initial'],c['type'])
 inputnames={c['name'] for c in s['inputs']}
 if written(s.get('program',[]))&inputnames:raise DesignError('输入不可赋值，请使用变量')
 g.statements(s['program'])
 output_types={}
 for c in s['outputs']:
  if set(c)!={'name','expression'}:raise DesignError('输出字段无效')
  claim(c['name']);net,typ=g.compile(tree(c['expression']));output_types[c['name']]=typ
  e,u=g.element('Indicator',{'_name':c['name'],'type':typ,'value':'[]' if typ.startswith('array{') else 'false' if typ=='bool' else '0','inputs':'value:'+net,'connection':'recommended'})
  if connector[c['name']] is not None:e.set('conIdx',str(connector[c['name']]))
 if not isinstance(s.get('tests'),list) or not 1<=len(s['tests'])<=12:raise DesignError('需1至12组测试')
 tests=[]
 for case in s['tests']:
  if not isinstance(case.get('inputs'),dict) or set(case['inputs'])!=inputnames:raise DesignError('测试输入不完整')
  env={c['name']:copy.deepcopy(value_check(case['inputs'][c['name']],c['type'])) for c in s['inputs']}
  try:
   for c in s['variables']:env[c['name']]=value_check(expr_value(c['initial'],env),c['type'])
   interpret(s['program'],env,types,[20000])
   expected={c['name']:value_check(expr_value(c['expression'],env),output_types[c['name']]) for c in s['outputs']}
   supplied=case.get('expected')
   if supplied is not None and (not isinstance(supplied,dict) or set(supplied)!=set(expected)):raise DesignError('测试预期字段不匹配')
   def equal(x,y):
    if isinstance(y,list):return isinstance(x,list) and len(x)==len(y) and all(equal(a,b) for a,b in zip(x,y))
    if type(y) is bool:return type(x) is bool and x==y
    return type(x) in (int,float) and math.isfinite(x) and abs(x-y)<=1e-8*max(1,abs(y))
   if supplied is not None and not all(equal(supplied[k],v) for k,v in expected.items()):raise DesignError('模型预期与独立结构化解释器不一致')
  except (ArithmeticError,KeyError,TypeError) as exc:raise DesignError('结构化测试求值失败：'+str(exc)) from None
  tests.append({'inputs':case['inputs'],'expected':expected})
 s['tests']=tests
 return s,ET.tostring(g.root,encoding='unicode')+'\n<?lvmcp pane="'+str(s['connector_pattern'])+'"?>',output_types

STRUCTURED_SCHEMA='''
For arrays, loops, state or events use this schema (not scalar schema):
{"kind":"structured","name":"AsciiVIName","description":"purpose only","inputs":[{"name":"Samples","type":"array{double}","default":[1.0,2.0]},{"name":"Commands","type":"array{int32}","default":[1,2]}],"variables":[{"name":"Buffer","type":"array{double}","initial":"[]"},{"name":"State","type":"int32","initial":"0"}],"program":[STATEMENTS],"outputs":[{"name":"Result","expression":"Buffer"}],"tests":[{"inputs":{"Samples":[1.0],"Commands":[1,2]},"expected":{"Result":[1.0]}}],"assumptions":[]}
Types: double,bool,int32,array{double},array{int32}. <=6 inputs,<=6 outputs,<=24 variables,<=500 nodes,12 connector slots. Literals 0 is int32, 0.0 is double; use double(x)/int32(x) casts where necessary. Do not assign inputs, only declared variables. Expressions also allow numeric array literals, array[index] (out of range gives0),len,sum,mean(empty=>0),append(array,item),concat(array,array), and previous scalar operators. No implicit array arithmetic, use for_each.
Statements:
{"op":"set","name":"Buffer","expression":"append(Buffer,1.0)"}
{"op":"if","condition":"len(Samples)>0","then":[...],"else":[...]}; actual Case Structure, lazy branches.
{"op":"for_each","array":"Samples","item":"sample","index":"i","body":[...],"collect":[{"name":"Buffer","expression":"sample*2.0"}]}; actual auto-indexed For Loop. collect replaces predeclared array, empty loop yields[]. Body may mutate other declared variables via real shift registers. Cannot reference collected array inside body; to accumulate manually omit collect and use append assignment.
{"op":"for","count":"int32(3)","index":"j","body":[...],"collect":[]}; actual count For Loop, clamped0..1024.
{"op":"while","until":"Done","max_iterations":100,"index":"iteration","body":[...]}; actual post-test While Loop, runs at least once, stops when until true or cap reached.
{"op":"state_machine","state":"State","states":[{"value":0,"name":"Idle","body":[...]},{"value":1,"name":"Running","body":[...]}],"default":[...]}; actual integer Case Structure. Use inside events or while to retain state. State values unique0..100. All branches carry all variables through.
{"op":"events","commands":"Commands","event":"Command","body":[...]}: only ONE top-level statement of this kind. Real producer For Loop creates an int32 User Event for each array command, parallel consumer While Loop+Event Structure reads Command payload and runs body sequentially with shift-register state. Internal reserved final event guarantees stop after commands. Commands <=64 elements, reserved -2147483648 forbidden. Not a simulation of an Event Structure: actual dynamic user-event registration, generation, handling and cleanup. Timeout frame exists but no timed Timeout or GUI button injection supported. Event body may contain state_machine, for_each, if etc. Event variable and loop item/index names must not collide with any declared name.
Give 3..6 tests including empty array, normal commands, reset or invalid ordering when relevant. Describe command IDs, states and cap semantics explicitly. Never claim hardware/GUI events not provided. Preserve structured kind and original behavior in modifications. Nested scope variables cannot escape except declared carried variables or collect results. Use separate output names from variable names. Return needs_clarification for unsupported features.
'''
