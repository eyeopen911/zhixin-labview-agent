"""Allowlisted NI demo executor. Model text is never evaluated or executed."""
import base64,hashlib,json,math,os,re,subprocess,sys,threading,uuid
from pathlib import Path
LOCK=threading.Lock()
ROOT=Path(__file__).resolve().parent
from settings import remote_host, windows_root, require_remote
REMOTE=remote_host()
WINROOT=windows_root()
PYTHON=os.environ.get('NI_AGENT_PYTHON',sys.executable)
def call(args,timeout=90):
    r=subprocess.run(args,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout)
    return r

def ps(code,timeout=90):
    # Only internal fixed commands reach this helper. Task parameters are numbers
    # or base64 JSON; model output and arbitrary script text never reach it.
    if '"' in code or '\n' in code:raise ValueError('Unexpected internal command format')
    return call(['ssh','-n','-T','-o','BatchMode=yes','-o','ConnectTimeout=8',REMOTE,
                 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); '+code+'"'],timeout)

def decode(r):
    lines=[x.split('NI_AGENT_RESULT:',1)[1] for x in r.stdout.splitlines() if x.startswith('NI_AGENT_RESULT:')]
    if len(lines)!=1:raise RuntimeError('NI tool returned no unique result')
    record=json.loads(lines[0])
    if record.get('ok') is not True:raise RuntimeError('NI validation failed')
    record['host_exit_code']=r.returncode
    if r.returncode:raise RuntimeError('NI host exited abnormally despite an intermediate result')
    return record

def dispatch(task,inputs):
    if task not in ('teststand_demo','offset_correction','scale_current'):raise RuntimeError('Unsupported task')
    require_remote()
    if task=='teststand_demo':raise RuntimeError('TestStand executor is not included in this LabVIEW source package')
    with LOCK:
        raw=inputs.get('RawCurrent');secondary=inputs.get('Offset' if task=='offset_correction' else 'Scale')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e12 for v in (raw,secondary)):raise ValueError('Invalid numerical inputs')
        run_id=uuid.uuid4().hex;out=ROOT/'artifacts'/run_id;out.mkdir(parents=True)
        template=ROOT/'examples'/('offset_correction.xml' if task=='offset_correction' else 'scale_current.xml')
        generated=out/'generated.vi'
        composed=call([PYTHON,str(ROOT/'scripts'/'compose_on_mac.py'),str(template),str(generated),'--lv-version','25'])
        if composed.returncode or not generated.is_file():raise RuntimeError('VI composer failed')
        remote_dir=WINROOT+'\\runs\\'+run_id
        if ps("New-Item -ItemType Directory -Force '"+remote_dir+"' | Out-Null").returncode:raise RuntimeError('Remote directory unavailable')
        dest=(WINROOT+'\\runs\\'+run_id+'\\generated.vi').replace('\\','/')
        if call(['scp',str(generated),REMOTE+':'+dest]).returncode:raise RuntimeError('VI transfer failed')
        request={'task':task,'run_id':run_id,'raw':raw,'secondary':secondary,'expected':raw-secondary if task=='offset_correction' else raw*secondary}
        payload=base64.b64encode(json.dumps(request,allow_nan=False).encode()).decode('ascii')
        record=decode(ps("& '"+WINROOT+r"\run-labview.ps1' -PayloadBase64 '"+payload+"'",85))
        if record.get('run_id')!=run_id or abs(record['actual']-request['expected'])>1e-9*max(1,abs(request['expected'])):raise RuntimeError('Result identity or arithmetic mismatch')
        if call(['scp',REMOTE+':'+dest,str(generated)]).returncode:raise RuntimeError('Verified artifact download failed')
        if hashlib.sha256(generated.read_bytes()).hexdigest()!=record['sha256'].lower():raise RuntimeError('Artifact digest mismatch')
        if not re.fullmatch('[a-f0-9]{32}',record.get('run_id','')):raise RuntimeError('Invalid result identity')
        out=ROOT/'artifacts'/record['run_id'];out.mkdir(parents=True,exist_ok=True)
        (out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        return record

# Exposes the real transport state to the local UI.
dispatch.remote = os.environ.get("NI_AGENT_ENABLE_REMOTE", "").lower() in ("1", "true")
