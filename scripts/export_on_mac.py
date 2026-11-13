#!/usr/bin/env python3
import pathlib,sys,os,re,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1];B=pathlib.Path(os.environ.get('NI_AGENT_LABVIEW_MCP_BIN') or str(ROOT/'tools/labview-mcp-release/package/bin'));S=B/'scripts/aixml-pylabview'
sys.path.insert(0,str(S));os.environ['PYTHONPATH']=str(B/'pylabview/app')
import lvheap
lvheap._pylabview_argv=lambda:[sys.executable,str(B/'pylabview/app/pylabview/readRSRC.py')]
import vi2aixml
from composer_gui_extension import install_export
install_export(vi2aixml)
vi2aixml.main(sys.argv[1:])
if len(sys.argv)>2:
 p=pathlib.Path(sys.argv[2]);text=p.read_text();root=ET.fromstring(text)
 for el in root.iter():
  for key in ('description','comment','label','_name'):
   if el.get(key):
    try:el.set(key,el.get(key).encode('mac_roman').decode('cp936'))
    except (UnicodeEncodeError,UnicodeDecodeError):pass
 p.write_text(ET.tostring(root,encoding='unicode')+'\n'+'\n'.join(re.findall(r'<\?lvmcp .*?\?>',text)))
