"""Read-only independent proof of persisted typeDef heap objects and control VI kind."""
import pathlib,sys,os,json,xml.etree.ElementTree as E
ROOT=pathlib.Path(__file__).resolve().parents[1];B=pathlib.Path(os.environ.get('NI_AGENT_LABVIEW_MCP_BIN') or str(ROOT/'tools/labview-mcp-release/package/bin'));S=B/'scripts/aixml-pylabview';sys.path.insert(0,str(S));os.environ['PYTHONPATH']=str(B/'pylabview/app')
import lvheap
lvheap._pylabview_argv=lambda:[sys.executable,str(B/'pylabview/app/pylabview/readRSRC.py')]
vi=pathlib.Path(sys.argv[1]);directory=pathlib.Path(sys.argv[2]);b=lvheap.Bundle(lvheap.extract(str(vi),str(directory)))
items={}
for prefix,heap in [('front_panel',b.fp),('block_diagram',b.bd)]:
 items[prefix]=[{'uid':e.get('uid'),'label':e.findtext('./partsList/SL__arrayElement[@class="label"]/textRec/text'),'xml':E.tostring(e,encoding='unicode'),'type_tree':E.tostring(b.heap_type_tree(int(__import__('re').search(r'\d+',e.findtext('typeDesc')).group())),encoding='unicode')} for e in heap.iter() if e.get('class')=='typeDef'] if heap is not None else []
items['execution']=b.main.find('LVSR/Section/Execution').attrib
items['instrument']=b.main.find('LVSR/Section/Instrument').attrib
print(json.dumps(items,ensure_ascii=False))
