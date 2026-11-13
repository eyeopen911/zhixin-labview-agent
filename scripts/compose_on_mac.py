#!/usr/bin/env python3
"""Upstream composer with macOS Python launcher and target-Windows text adaptation.
Keep binary heap DefaultData in donor MacRoman; transcode only human text attributes.
"""
import importlib.util,pathlib,sys,os,tempfile,re,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1];B=pathlib.Path(os.environ.get('NI_AGENT_LABVIEW_MCP_BIN') or str(ROOT/'tools/labview-mcp-release/package/bin'));S=B/'scripts/aixml-pylabview'
sys.path.insert(0,str(S));os.environ['PYTHONPATH']=str(B/'pylabview/app')
import lvheap
lvheap._pylabview_argv=lambda:[sys.executable,str(B/'pylabview/app/pylabview/readRSRC.py')]
spec=importlib.util.spec_from_file_location('aixml2vi',S/'aixml2vi.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from composer_gui_extension import install
install(m)
args=sys.argv[1:];original=pathlib.Path(args[0]).read_text();root=ET.fromstring(original)
from engineering_layout import install as install_engineering
install_engineering(m,'<?lvmcp engineering="true"?>' in original)
for element in root.iter():
 for key in ('description','comment','label','_name'):
  if element.get(key):element.set(key,element.get(key).encode('cp936').decode('mac_roman'))
with tempfile.TemporaryDirectory(prefix='ni-aixml-text-') as work:
 src=pathlib.Path(work)/'design.aixml';src.write_text(ET.tostring(root,encoding='unicode')+'\n'+'\n'.join(re.findall(r'<\?lvmcp .*?\?>',original)))
 args[0]=str(src);raise SystemExit(m.main(args))
