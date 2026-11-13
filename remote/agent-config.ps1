function Get-AgentRoot {
 if($env:NI_AGENT_WINDOWS_ROOT){return $env:NI_AGENT_WINDOWS_ROOT}
 return $PSScriptRoot
}
function Get-AgentInterop {
 if($env:NI_AGENT_INTEROP_DLL){$file=$env:NI_AGENT_INTEROP_DLL}
 else{$file=Join-Path (Get-AgentRoot) 'interop\LabVIEW.Automation.dll'}
 if(!(Test-Path -LiteralPath $file)){throw 'Provide an authorized LabVIEW Automation interop assembly locally. It is not distributed by this repository.'}
 return $file
}
