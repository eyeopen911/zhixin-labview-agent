param([string]$RunId)
$ErrorActionPreference='Stop'
if($RunId -notmatch '^[a-f0-9]{32}$'){throw 'Invalid run id'}
. (Join-Path $PSScriptRoot 'agent-config.ps1')
$root=Get-AgentRoot;$dir=Join-Path $root ('runs\'+$RunId)
if(!(Test-Path (Join-Path $dir 'request.json'))){throw 'Request missing'}
$svc=New-Object -ComObject 'Schedule.Service';$svc.Connect();$folder=$svc.GetFolder('\');$def=$svc.NewTask(0)
$def.Principal.UserId=[Security.Principal.WindowsIdentity]::GetCurrent().Name;$def.Principal.LogonType=3;$def.Settings.ExecutionTimeLimit='PT4M';$def.Settings.DisallowStartIfOnBatteries=$false;$def.Settings.StopIfGoingOnBatteries=$false
$a=$def.Actions.Create(0);$a.Path='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe';$a.Arguments='-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$root+'\generic-worker.ps1" -RunDir "'+$dir+'"'
$job=$folder.RegisterTaskDefinition('ZhixinNI_Agent_GenericVI',$def,6,[Security.Principal.WindowsIdentity]::GetCurrent().Name,$null,3,$null);$job.Run($null)|Out-Null
for($i=0;$i -lt 300;$i++){if(Test-Path (Join-Path $dir 'result.json')){break};Start-Sleep -Milliseconds 500}
if(!(Test-Path (Join-Path $dir 'result.json'))){throw 'Worker timed out'}
$record=Get-Content (Join-Path $dir 'result.json') -Raw|ConvertFrom-Json
'NI_AGENT_RESULT:'+($record|ConvertTo-Json -Depth 15 -Compress)
if(!$record.ok){exit 1};exit 0
