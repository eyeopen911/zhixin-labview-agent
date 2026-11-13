param([string]$PayloadBase64)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'agent-config.ps1')
$root=Get-AgentRoot
$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($PayloadBase64))|ConvertFrom-Json
if($p.task -notin @('offset_correction','scale_current') -or $p.run_id -notmatch '^[a-f0-9]{32}$'){throw 'Unsupported request'}
$dir=Join-Path $root ('runs\'+$p.run_id)
if(!(Test-Path (Join-Path $dir 'generated.vi'))){throw 'Generated VI missing'}
$p|ConvertTo-Json -Compress|Set-Content (Join-Path $dir 'request.json') -Encoding UTF8
$svc=New-Object -ComObject 'Schedule.Service';$svc.Connect();$folder=$svc.GetFolder('\');$def=$svc.NewTask(0)
$def.Principal.UserId=[Security.Principal.WindowsIdentity]::GetCurrent().Name;$def.Principal.LogonType=3;$def.Settings.ExecutionTimeLimit='PT2M';$def.Settings.DisallowStartIfOnBatteries=$false;$def.Settings.StopIfGoingOnBatteries=$false
$a=$def.Actions.Create(0);$a.Path='C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe';$a.Arguments='-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$root+'\tool-worker.ps1" -RunDir "'+$dir+'"'
$job=$folder.RegisterTaskDefinition('ZhixinNI_Agent_Demo',$def,6,[Security.Principal.WindowsIdentity]::GetCurrent().Name,$null,3,$null);$job.Run($null)|Out-Null
for($i=0;$i -lt 120;$i++){if(Test-Path (Join-Path $dir 'result.json')){break};Start-Sleep -Milliseconds 500}
if(!(Test-Path (Join-Path $dir 'result.json'))){throw 'Worker timed out'}
$record=Get-Content (Join-Path $dir 'result.json') -Raw|ConvertFrom-Json
if(!$record.ok){'NI_AGENT_RESULT:'+($record|ConvertTo-Json -Compress);exit 1}
'NI_AGENT_RESULT:'+($record|ConvertTo-Json -Compress)
exit 0
