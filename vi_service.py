"""Persistent design revisions and verified NI build jobs."""
import base64,copy,difflib,hashlib,json,re,secrets,subprocess,threading,time,uuid,traceback,xml.etree.ElementTree as ET
from pathlib import Path
from settings import require_remote
from vi_design import DesignError,validate_spec,model_design,import_aixml
from dispatcher import ROOT,WINROOT,REMOTE,PYTHON,call,ps,decode,LOCK
STORE=ROOT/'designs';STORE.mkdir(exist_ok=True)
def identity(s):
    if not isinstance(s,str) or not re.fullmatch('[a-f0-9]{32}',s):raise DesignError('设计编号无效')
    return s

def load(design_id):
    path=STORE/identity(design_id)/'design.json'
    if not path.is_file():raise DesignError('找不到设计版本')
    return json.loads(path.read_text())

def save(spec,xml,types,prompt='',parent=None,origin=None):
    i=uuid.uuid4().hex;d=STORE/i;d.mkdir()
    before=load(parent)['spec'] if parent else None
    diff='\n'.join(difflib.unified_diff(json.dumps(before,ensure_ascii=False,indent=2).splitlines() if before else [],json.dumps(spec,ensure_ascii=False,indent=2).splitlines(),fromfile='previous',tofile='proposed',lineterm=''))
    record={'id':i,'parent_id':parent,'created_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'prompt':prompt,'spec':spec,'output_types':types,'status':'designed','diff':diff,'origin':origin,'notice':'尚未在 LabVIEW 中执行；修改版本另存，源 VI 不覆盖。'}
    (d/'design.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));(d/'design.aixml').write_text(xml)
    return record

def propose(prompt,model,base_id=None):
    current=load(base_id)['spec'] if base_id else None
    spec,xml,types=model_design(prompt,model,current)
    if current and current.get('engineering'):spec['engineering']=True
    if current and current.get('shared_typedefs'):spec['shared_typedefs']=True
    return save(spec,xml,types,prompt,base_id)

def list_designs():
    result=[]
    for p in STORE.glob('*/design.json'):
        try:r=json.loads(p.read_text());result.append({k:r[k] for k in ('id','parent_id','created_at','status')}|{'name':r['spec']['name']})
        except (ValueError,KeyError):continue
    return sorted(result,key=lambda r:r['created_at'],reverse=True)[:100]

def import_vi(filename,data):
    if not isinstance(filename,str) or not filename.lower().endswith('.vi'):raise DesignError('请选择 .vi 文件')
    try:binary=base64.b64decode(data,validate=True)
    except (ValueError,TypeError):raise DesignError('文件内容无效') from None
    if not 100<=len(binary)<=4*1024*1024:raise DesignError('VI 文件大小须为 100 字节至 4 MiB')
    # Uploaded names never become OS command text or paths.
    i=uuid.uuid4().hex;d=ROOT/'imports'/i;d.mkdir(parents=True)
    source=d/'original.vi';source.write_bytes(binary);export=d/'original.aixml'
    r=call([PYTHON,str(ROOT/'scripts/export_on_mac.py'),str(source),str(export)],60)
    if r.returncode or not export.is_file():raise DesignError('无法导出 VI。加密、无框图或依赖未解析的 VI 暂不支持')
    digest=hashlib.sha256(binary).hexdigest()
    for result_file in (ROOT/'artifacts').glob('*/result.json'):
        try:
            registered=json.loads(result_file.read_text())
            if registered.get('sha256','').lower()!=digest:continue
            source_spec=json.loads((result_file.parent/'spec.json').read_text())
            if source_spec.get('kind') not in ('structured','gui'):continue
            spec,xml,types=validate_spec(source_spec)
            return save(spec,xml,types,prompt='导入已验证的结构化 VI',origin={'import_id':i,'filename':Path(filename).name,'sha256':digest,'registered_build_id':result_file.parent.name,'layout_notice':'使用与二进制哈希严格对应的结构化设计；修改仍会重建布局。'})
        except (ValueError,OSError,KeyError):continue
    spec,xml,types=import_aixml(export.read_text())
    clean=re.sub('[^A-Za-z0-9_]','_',Path(filename).stem)
    if not clean or not clean[0].isalpha():clean='Imported_'+clean
    spec['name']=clean[:40];spec,xml,types=validate_spec(spec)
    return save(spec,xml,types,prompt='导入现有 VI',origin={'import_id':i,'filename':Path(filename).name,'sha256':hashlib.sha256(binary).hexdigest(),'layout_notice':'修改会重建布局；原始文件完整保留。'})

class BuildManager:
    def __init__(self):self.jobs={};self.lock=threading.Lock()
    def start(self,design_id):
        try:require_remote()
        except RuntimeError as error:raise DesignError(str(error)) from None
        r=load(design_id);spec,xml,types=validate_spec(r['spec'])
        with self.lock:
            if sum(j['status'] in ('queued','running') for j in self.jobs.values())>=4:raise DesignError('已有 4 个任务等待执行')
            job={'id':uuid.uuid4().hex,'design_id':design_id,'status':'queued','executed':False};self.jobs[job['id']]=job
        threading.Thread(target=self._run,args=(job,spec,xml,types),daemon=True).start();return copy.deepcopy(job)
    def get(self,i):
        with self.lock:
            if i not in self.jobs:raise DesignError('找不到构建任务')
            return copy.deepcopy(self.jobs[i])
    def _run(self,job,spec,xml,types):
        start=time.monotonic()
        with self.lock:job['status']='running'
        out=ROOT/'artifacts'/job['id'];out.mkdir(parents=True)
        try:
            with LOCK:
                modules={}
                if spec.get('engineering'):
                    from vi_engineering import compile_project
                    xml,modules=compile_project(spec,job['id'][:8])
                filename=spec['name']+'_'+job['id'][:8]+'.vi';vi=out/filename
                (out/'design.aixml').write_text(xml);(out/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2))
                module_dir=out/'Modules';module_dir.mkdir(exist_ok=True)
                for name,source in modules.items():
                    module_xml=module_dir/(name+'.aixml');module_xml.write_text(source)
                    result=call([PYTHON,str(ROOT/'scripts/compose_on_mac.py'),str(module_xml),str(module_dir/name),'--lv-version','25'],60)
                    (module_dir/(name+'.log')).write_text(result.stdout+'\n'+result.stderr)
                    if result.returncode:raise DesignError('子VI编译失败：'+name)
                r=call([PYTHON,str(ROOT/'scripts/compose_on_mac.py'),str(out/'design.aixml'),str(vi),'--lv-version','25','--search',str(module_dir)],60)
                (out/'composer.log').write_text(r.stdout+'\n'+r.stderr)
                if r.returncode or not vi.is_file():raise DesignError('VI 编译失败，请查看工件目录中的 composer.log')
                dest=(WINROOT+'\\runs\\'+job['id']).replace('\\','/');win=WINROOT+'\\runs\\'+job['id']
                if ps("New-Item -ItemType Directory -Force '"+win+"' | Out-Null").returncode:raise DesignError('远端演示目录不可用')
                if modules:
                    if ps("New-Item -ItemType Directory -Force '"+win+"\\Modules' | Out-Null").returncode:raise DesignError('远端子VI目录不可用')
                    for name in modules:
                        if call(['scp',str(module_dir/name),REMOTE+':'+dest+'/Modules/'+name]).returncode:raise DesignError('子VI上传失败')
                typedef_manifest=None
                if spec.get('shared_typedefs'):
                    from vi_typedef import manifest
                    typedef_manifest,carriers=manifest(spec,modules,filename);type_dir=out/'Types';type_dir.mkdir()
                    if ps("New-Item -ItemType Directory -Force '"+win+"\\Types' | Out-Null").returncode:raise DesignError('远端类型目录不可用')
                    for name,source in carriers.items():
                        src=type_dir/(name+'.aixml');src.write_text(source);result=call([PYTHON,str(ROOT/'scripts/compose_on_mac.py'),str(src),str(type_dir/name),'--lv-version','25'],60)
                        (type_dir/(name+'.log')).write_text(result.stdout+'\n'+result.stderr)
                        if result.returncode:raise DesignError('类型载体编译失败')
                        if call(['scp',str(type_dir/name),REMOTE+':'+dest+'/Types/'+name]).returncode:raise DesignError('类型载体上传失败')
                    (out/'typedef-manifest.json').write_text(json.dumps(typedef_manifest,ensure_ascii=False,indent=2))
                request={'typedef_files':[t['file'] for t in typedef_manifest['types'].values()] if typedef_manifest else [],'typedef_manifest':typedef_manifest,'module_files':list(modules),'filename':filename,'tests':spec['tests'],'output_types':types,'input_types':{c['name']:c['type'] for c in spec['inputs']}}
                if spec.get('kind')=='structured' and 'Event Structure' in xml:request['runtime_checks']={'NI_RuntimeError':0,'NI_RuntimeStatus':False}
                if spec.get('kind')=='gui':
                    from vi_gui import INTERNAL
                    from vi_structured import expr_value
                    request['gui_buttons']=[b['name'] for b in spec['buttons']]
                    request['gui_intervals']=[expr_value(spec['timeout']['interval'],case['inputs']) for case in spec['tests']]
                (out/'request.json').write_text(json.dumps(request,ensure_ascii=False))
                for p in (vi,out/'request.json'):
                    if call(['scp',str(p),REMOTE+':'+dest+'/'+p.name]).returncode:raise DesignError('远端传输失败')
                r=ps("& '"+WINROOT+r"\run-generic.ps1' -RunId '"+job['id']+"'",175)
                (out/'worker.log').write_text(r.stdout+'\n'+r.stderr)
                # Preserve exact structured failures, without exposing arbitrary process output to UI.
                try:record=decode(r)
                except Exception:
                    lines=[l.partition('NI_AGENT_RESULT:')[2] for l in r.stdout.splitlines() if l.startswith('NI_AGENT_RESULT:')]
                    detail=json.loads(lines[0]).get('detail','') if len(lines)==1 else ''
                    raise DesignError('LabVIEW 实际验证失败'+('：'+str(detail)[:500] if detail else '，请确认远端桌面已登录并查看 worker.log')) from None
                if record.get('run_id')!=job['id'] or len(record.get('cases',[]))!=len(spec['tests']):raise DesignError('验证记录身份或用例数不匹配')
                if call(['scp',REMOTE+':'+dest+'/'+filename,str(vi)]).returncode:raise DesignError('验证后 VI 下载失败')
                if hashlib.sha256(vi.read_bytes()).hexdigest()!=record.get('sha256','').lower():raise DesignError('下载文件哈希不匹配')
                observed=out/'verified.aixml'
                exported=call([PYTHON,str(ROOT/'scripts/export_on_mac.py'),str(vi),str(observed)],30)
                if exported.returncode or not observed.is_file():raise DesignError('无法读取验证后 VI 的连接器信息')
                parsed=ET.fromstring(observed.read_text())
                internal={'NI_RuntimeError','NI_RuntimeStatus'} if request.get('runtime_checks') else set()
                if spec.get('kind')=='gui':
                    from vi_gui import INTERNAL
                    internal=set(INTERNAL)|set(request['gui_buttons'])
                actual_ports={e.get('_name'):int(e.get('conIdx')) if e.get('conIdx','-1').isdigit() else None for e in parsed.iter() if e.tag in ('Control','Indicator') and e.get('_name') not in internal}
                if actual_ports!=spec['connector']:raise DesignError('VI 实际连接器与设计映射不一致')
                actual_inputs={e.get('_name'):e.get('type') for e in parsed.iter() if e.tag=='Control' and e.get('_name') not in internal}
                actual_outputs={e.get('_name'):e.get('type') for e in parsed.iter() if e.tag=='Indicator' and e.get('_name') not in internal}
                if actual_inputs!={c['name']:c['type'] for c in spec['inputs']} or actual_outputs!=types:raise DesignError('VI 实际输入输出类型不一致')
                pane_match=re.search(r'<\?lvmcp pane="(\d+)"',observed.read_text())
                if not pane_match or int(pane_match.group(1))!=spec['connector_pattern']:raise DesignError('VI 实际连接器图案不一致')
                expected_root=ET.fromstring(xml)
                expected_structures={name:sum(e.tag=='Structure' and e.get('_name')==name for e in expected_root.iter()) for name in ('For Loop','While Loop','Case Structure','Event Structure')}
                record['structures_verified']={name:sum(e.tag=='Structure' and e.get('_name')==name for e in parsed.iter()) for name in ('For Loop','While Loop','Case Structure','Event Structure')}
                if record['structures_verified']!=expected_structures:raise DesignError('保存后的实际程序结构与设计不一致')
                record['connector_verified']=True;record['connector']=actual_ports;record['connector_pattern']=int(pane_match.group(1))
                if spec.get('kind')=='gui':
                    events=[e for e in parsed.iter() if e.tag=='Structure' and e.get('_name')=='Event Structure']
                    if len(events)!=1 or not events[0].get('timeout'):raise DesignError('保存后GUI Timeout端子未实际连线')
                    selectors=[e.get('selector','') for e in events[0] if e.tag=='CaseFrame']
                    if not any('Timeout' in x for x in selectors):raise DesignError('GUI缺少Timeout分支')
                    for name in request['gui_buttons']:
                        if not any(name in x and 'Value Change' in x for x in selectors):raise DesignError('GUI按钮未实际注册Value Change：'+name)
                    record['gui_events_verified']=selectors;record['timeout_wired']=True
                    from PIL import Image
                    for prefix in ('front-panel','block-diagram'):
                        for suffix in ('.raw','-meta.json'):
                            filename_image=prefix+suffix
                            if call(['scp',REMOTE+':'+dest+'/'+filename_image,str(out/filename_image)]).returncode:raise DesignError('原生图像下载失败')
                        meta=json.loads((out/(prefix+'-meta.json')).read_text(encoding='utf-8-sig'))
                        width,height=int(meta['width']),int(meta['height']);raw=(out/(prefix+'.raw')).read_bytes()
                        if meta['depth']!=24 or width<=0 or height<=0 or len(raw)%height:raise DesignError('原生图像格式无效')
                        stride=len(raw)//height
                        if not width*3<=stride<=width*3+8:raise DesignError('原生图像尺寸不匹配')
                        Image.frombytes('RGB',(width,height),raw,'raw','RGB',stride,1).save(out/(prefix+'.png'))
                    record['images']={n:'/api/vi/image/'+job['id']+'/'+n+'.png' for n in ('front-panel','block-diagram')}
                if modules:
                    # Retrieve the native-saved subVIs, validate every binary hash, and retain real diagrams.
                    r=call(['scp']+[REMOTE+':'+dest+'/Modules/'+name for name in modules]+[str(module_dir)])
                    if r.returncode:raise DesignError('已验证子VI下载失败')
                    for name in modules:
                        if hashlib.sha256((module_dir/name).read_bytes()).hexdigest()!=record.get('module_sha256',{}).get(name,'').lower():raise DesignError('子VI哈希核对失败：'+name)
                    if call(['scp','-r',REMOTE+':'+dest+'/subvi-images',str(out)]).returncode:raise DesignError('子VI原生图像下载失败')
                    for meta_file in (out/'subvi-images').glob('*/*-meta.json'):
                        prefix=meta_file.name.replace('-meta.json','');meta=json.loads(meta_file.read_text(encoding='utf-8-sig'));raw=(meta_file.parent/(prefix+'.raw')).read_bytes();Image.frombytes('RGB',(meta['width'],meta['height']),raw,'raw','RGB',len(raw)//meta['height'],1).save(meta_file.parent/(prefix+'.png'))
                    record['subvis_verified']=[e.get('target') for e in parsed.iter() if e.tag=='Call']
                    if {Path(x).name for x in record['subvis_verified']}!=set(modules):raise DesignError('实际子VI调用与工程清单不一致')
                    if typedef_manifest:
                        type_dir=out/'Types'
                        type_names=[t['file'] for t in typedef_manifest['types'].values()]
                        if call(['scp']+[REMOTE+':'+dest+'/Types/'+n for n in type_names]+[str(type_dir)]).returncode:raise DesignError('共享typedef下载失败')
                        if call(['scp',REMOTE+':'+dest+'/typedef-verification.json',str(out/'typedef-verification.json')]).returncode:raise DesignError('typedef身份检查记录下载失败')
                        td=json.loads((out/'typedef-verification.json').read_text(encoding='utf-8-sig'))
                        if len(td['identity_checks'])!=len(typedef_manifest['bindings']):raise DesignError('typedef链接读回数不匹配')
                        for name in type_names:
                            if hashlib.sha256((type_dir/name).read_bytes()).hexdigest()!=record.get('typedef_sha256',{}).get(name,'').lower():raise DesignError('typedef哈希不匹配')
                        # Persisted heap objects, not stale VCTP wrappers, establish real binary bindings.
                        proofs=[]
                        for rel in [filename]+sorted({b['file'] for b in typedef_manifest['bindings'] if not b['constant']})+['Types/'+n for n in type_names]:
                            proof=call([PYTHON,str(ROOT/'scripts/inspect_typedef_binary.py'),str(out/rel),str(out/'type-proof'/Path(rel).stem)],45)
                            if proof.returncode:raise DesignError('typedef二进制检查失败：'+rel)
                            detail=json.loads(proof.stdout);(out/'type-proof'/(Path(rel).stem+'.json')).write_text(json.dumps(detail,ensure_ascii=False,indent=2))
                            from vi_typedef import instance_count,verify_field_tree
                            expected_count=sum(instance_count(typedef_manifest['types'],b['typedef']) for b in typedef_manifest['bindings'] if b['file']==rel);count=len(detail['block_diagram'] if rel==filename else detail['front_panel'])
                            if rel.startswith('Types/'):
                                if detail['instrument']['Type']!='Control' or detail['execution'].get('TypeDefVI')!='1':raise DesignError('保存的.ctl不是实际typedef')
                            elif count!=expected_count:raise DesignError('保存文件中的真实typedef对象数不匹配：'+rel)
                            for item in detail['block_diagram'] if rel==filename else detail['front_panel']:
                                label=(item['label'] or '').strip('"');matches=[b['typedef'] for b in typedef_manifest['bindings'] if b['file']==rel and b['object']==label]
                                if not matches:matches=[n['typedef'] for n in typedef_manifest.get('nested_bindings',[]) if n['field']==label]
                                if len(set(matches))!=1:raise DesignError('typedef实例未对应唯一共享定义')
                                try:verify_field_tree(ET.fromstring(item['type_tree']),typedef_manifest['types'][matches[0]],typedef_manifest['types'])
                                except ValueError as e:raise DesignError(str(e)) from None
                            proofs.append({'file':rel,'front_panel_instances':len(detail['front_panel']),'block_diagram_instances':len(detail['block_diagram']),'typedef_vi':detail['execution'].get('TypeDefVI')})
                        if call(['scp','-r',REMOTE+':'+dest+'/typedef-images',str(out)]).returncode:raise DesignError('typedef真实图像下载失败')
                        for meta_file in (out/'typedef-images').glob('*/*-meta.json'):
                            meta=json.loads(meta_file.read_text(encoding='utf-8-sig'));raw=(meta_file.parent/'front-panel.raw').read_bytes();Image.frombytes('RGB',(meta['width'],meta['height']),raw,'raw','RGB',len(raw)//meta['height'],1).save(meta_file.parent/'front-panel.png')
                        record['shared_typedefs_verified']={'native_checks':td,'saved_binary_checks':proofs}
                    import zipfile
                    project=ET.Element('Project',{'Type':'Project','LVVersion':'25008000'});computer=ET.SubElement(project,'Item',{'Name':'My Computer','Type':'My Computer'});ET.SubElement(computer,'Item',{'Name':filename,'Type':'VI','URL':filename});folder=ET.SubElement(computer,'Item',{'Name':'Modules','Type':'Folder'})
                    for name in modules:ET.SubElement(folder,'Item',{'Name':name,'Type':'VI','URL':'Modules/'+name})
                    if typedef_manifest:
                        tf=ET.SubElement(computer,'Item',{'Name':'Types','Type':'Folder'})
                        for t in typedef_manifest['types'].values():ET.SubElement(tf,'Item',{'Name':t['file'],'Type':'VI','URL':'Types/'+t['file']})
                    ET.SubElement(computer,'Item',{'Name':'Dependencies','Type':'Dependencies'});ET.SubElement(computer,'Item',{'Name':'Build Specifications','Type':'Build'})
                    (out/'SampleControl.lvproj').write_text(ET.tostring(project,encoding='unicode'))
                    (out/'ENGINEERING_README.md').write_text('# 定时采样 GUI 工程\n\n打开 SampleControl.lvproj，再打开项目内主 VI。需要 LabVIEW 2025 或更新版本；本工程已在 25.3.2f2 实际执行验证，不依赖硬件。\n\nStart 启动或继续；Stop 暂停；Reset 停止并清空结果；Exit 正常退出。每个实际 Timeout 处理一个样本，完成后自动暂停。输入 Samples 为原始样本，Gain/Offset/Limit 为处理参数，IntervalMs 为事件等待间隔（20..2000 ms）。完整业务规则、独立预期和动作序列见 spec.json。\n\nModules 中：ConfigurePanel 初始化数组显示并返回初始化状态；HandleCommand 处理按钮命令；ProcessTimeout 处理一次定时运算；UpdateDiagnostics 更新计数与计时证据；NormalizeTimeout 规范化定时参数；EvaluateDisplay 计算显示值和退出条件。应用状态与诊断状态各用一个移位寄存器簇。文件名后缀用于避免同名 VI 在 LabVIEW 内存中绑定到其他版本。\n\n当前是可运行、可编辑的生成工程。状态簇由同一结构化设计生成，尚未提取为共享 typedef .ctl；没有硬件、驱动、DAQ、生产数据存储或安装程序。修改建议通过助手建立新版本并重新验证；编译器会重建布局，不能保留任意手工添加的节点。\n\nverification.json 包含真实按钮事件、定时采样间隔、预期/实际结果及主 VI 与子 VI 的 SHA-256。不要单独移动主 VI，须连同 Modules 目录使用。\n')
                    if typedef_manifest:
                        p=out/'ENGINEERING_README.md';p.write_text(p.read_text().replace('状态簇由同一结构化设计生成，尚未提取为共享 typedef .ctl','状态簇通过 Types 目录的 ApplicationState 和 DiagnosticsState 共享 typedef .ctl 绑定，端子与种子常量的链接、字段及保存后的二进制均已核对'))
                    (out/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
                    with zipfile.ZipFile(out/'LabVIEW_Project.zip','w',zipfile.ZIP_DEFLATED) as z:
                        for f in [vi,out/'SampleControl.lvproj',out/'spec.json',out/'ENGINEERING_README.md',out/'verification.json']+[module_dir/n for n in modules]+([out/'typedef-manifest.json',out/'typedef-verification.json']+[type_dir/t['file'] for t in typedef_manifest['types'].values()] if typedef_manifest else []):z.write(f,f.relative_to(out))
                    record['project_package']=str(out/'LabVIEW_Project.zip')
                record['elapsed_seconds']=round(time.monotonic()-start,2);record['local_artifact']=str(vi)
                (out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
                revision=load(job['design_id']);revision.update(status='verified',last_build_id=job['id']);(STORE/job['design_id']/'design.json').write_text(json.dumps(revision,ensure_ascii=False,indent=2))
                with self.lock:job.update(status='completed',executed=True,result=record,download_url='/api/vi/artifact/'+job['id'])
        except Exception as e:
            (out/'diagnostic.txt').write_text(traceback.format_exc())
            error=str(e) if isinstance(e,DesignError) else '构建执行异常；请查看本地工件记录'
            (out/'failure.json').write_text(json.dumps({'error':error},ensure_ascii=False))
            with self.lock:job.update(status='failed',executed=False,error=error)
