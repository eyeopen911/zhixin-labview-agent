param([string]$RunDir)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'agent-config.ps1')
$root=Get-AgentRoot
[TypedefWorker]::PrepareJson($RunDir,(Join-Path $root 'gui-tools'),(Get-Content (Join-Path $RunDir 'request.json') -Raw))|Set-Content (Join-Path $RunDir 'typedef-verification.json') -Encoding UTF8
