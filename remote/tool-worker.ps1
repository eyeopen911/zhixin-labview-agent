param([string]$RunDir)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'agent-config.ps1')
$root=Get-AgentRoot
try {
$p=Get-Content (Join-Path $RunDir 'request.json') -Raw|ConvertFrom-Json
if($p.task -notin @('offset_correction','scale_current')){throw 'Unsupported task'}
Add-Type -Path (Get-AgentInterop)
Add-Type -Path (Join-Path $root 'ToolWorker.cs') -ReferencedAssemblies (Get-AgentInterop)
$file=Join-Path $RunDir 'generated.vi'
$actual=[ToolWorker]::RunVI($file,[string]$p.task,[double]$p.raw,[double]$p.secondary)
$record=@{ok=$true;task=$p.task;actual=$actual;expected=[double]$p.expected;artifact=$file;sha256=(Get-FileHash $file -Algorithm SHA256).Hash;simulation_only=$true;run_id=(Split-Path $RunDir -Leaf)}
} catch {$record=@{ok=$false;error='LabVIEW generation or validation failed';detail=$_.Exception.Message}}
$record|ConvertTo-Json -Compress|Set-Content (Join-Path $RunDir 'result.json') -Encoding UTF8
