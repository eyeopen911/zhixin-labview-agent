"""Small local extension: explicitly wire the existing NI eventTimeOut terminal.
No modification to upstream vendored sources. AIXML extension attribute: timeout=<net>.
"""
def install(composer_module):
 C=composer_module.Composer;old_add=C.add_event;old_ends=C.endpoints
 def add_event(self,el):
  old_add(self,el)
  if el.get('timeout'):
   node=self.events[-1][0];matches=[t for t in node.find('termList') if t.find('dco') is not None and t.find('dco').get('class')=='eventTimeOut']
   if len(matches)!=1:raise composer_module.Unsupported('Expected exactly one event timeout terminal')
   self.ends[(el.get('uid'),'timeout')]=(matches[0].get('uid'),self.diag_of(el))
   self.report.append('Local extension: wired Event Structure Timeout')
 def endpoints(self,el):
  sources,sinks=old_ends(self,el)
  if el.tag=='Structure' and el.get('_name')=='Event Structure' and el.get('timeout'):sinks=sinks+[(el.get('timeout'),(el.get('uid'),'timeout'))]
  return sources,sinks
 C.add_event=add_event;C.endpoints=endpoints

def install_export(reader_module):
 old=reader_module.Reader.read
 def read(self):
  root=old(self);by={e.get('uid'):e for e in root.iter()}
  for tu,uid,kind in getattr(self,'event_timeouts',[]):
   if kind=='Event Structure' and tu in self.term_net and uid in by:by[uid].set('timeout',self.term_net[tu])
  self.notes=[x for x in self.notes if 'its wired timeout is not carried by AIXML' not in x]
  return root
 reader_module.Reader.read=read
