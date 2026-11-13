"""Map flat typed business variables to one-level nested, shared state definitions."""
from vi_design import DesignError,NAME
from vi_structured import expr_value

def cluster_type(fields):return 'cluster{'+','.join(t+'.'+n for n,t in fields)+'}'
def zero(t):return [] if t.startswith('array{') else False if t=='bool' else 0

def state_layout(s):
 flat=[(v['name'],v['type']) for v in s['variables']];types=dict(flat);groups=s.get('state_groups',[])
 if not isinstance(groups,list) or len(groups)>1:raise DesignError('当前支持一个一级嵌套状态typedef分组')
 used=set();group_defs={}
 for group in groups:
  if set(group)!={'name','fields'} or not isinstance(group['name'],str) or not NAME.fullmatch(group['name']) or group['name'] in types or group['name'] in ('ApplicationState','DiagnosticsState'):raise DesignError('嵌套状态分组名称无效')
  members=group['fields']
  if not isinstance(members,list) or not members or any(not isinstance(n,str) or n not in types or n in used for n in members) or len(set(members))!=len(members):raise DesignError('嵌套分组字段不存在或重复')
  used.update(members);group_defs[group['name']]=[(n,types[n]) for n in members]
 physical=[(n,t) for n,t in flat if n not in used]+[(n,cluster_type(f)) for n,f in group_defs.items()]
 paths={n:n for n,t in flat}
 for group,fields in group_defs.items():
  for n,t in fields:paths[n]=group+'.'+n
 def values(mapping):return [mapping[n] if n not in group_defs else [mapping[k] for k,t in group_defs[n]] for n,t in physical]
 return {'flat':flat,'physical':physical,'type':cluster_type(physical),'paths':paths,'groups':group_defs,'initial':values({v['name']:expr_value(v['initial'],{}) for v in s['variables']}),'defaults':values({n:zero(t) for n,t in flat})}
