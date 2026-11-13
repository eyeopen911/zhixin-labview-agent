param([string]$RunDir)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'agent-config.ps1')
$root=Get-AgentRoot
function Assert-Value($actual,$expected,[string]$type,[string]$name){
 if($type.StartsWith('array{')){
  if($null -eq $actual){$actual=@()};if($null -eq $expected){$expected=@()}
  if(@($actual).Count -ne @($expected).Count){throw ('Array length mismatch: '+$name)}
  $elementType=$type.Substring(6,$type.Length-7)
  for($j=0;$j -lt @($expected).Count;$j++){Assert-Value $actual[$j] $expected[$j] $elementType ($name+'['+$j+']')}
 } elseif($type -eq 'bool'){
  if($actual -isnot [bool] -or $actual -ne [bool]$expected){throw ('Boolean mismatch: '+$name)}
 } else {
  $v=[Convert]::ToDouble($actual);$x=[double]$expected
  if([double]::IsNaN($v) -or [double]::IsInfinity($v) -or [Math]::Abs($v-$x) -gt 1e-8*[Math]::Max(1,[Math]::Abs($x))){throw ('Output mismatch: '+$name)}
 }
}
try {
 $p=Get-Content (Join-Path $RunDir 'request.json') -Raw|ConvertFrom-Json
 Add-Type -Path (Get-AgentInterop)
 if($p.gui_buttons){$sources=@((Join-Path $root 'GenericWorker.cs'),(Join-Path $root 'GuiWorker.cs'))}else{$sources=@((Join-Path $root 'GenericWorker.cs'))}
 if($p.typedef_manifest){$sources+=Join-Path $root 'TypedefWorker.cs'}
 Add-Type -Path $sources -ReferencedAssemblies @((Get-AgentInterop),'System.Web.Extensions')
 if($p.typedef_manifest){& (Join-Path $root 'prepare-typedefs.ps1') -RunDir $RunDir}
 $compileBefore=$null;if($p.typedef_manifest){$compileBefore=([TypedefWorker]::ValidateJson($RunDir,(Join-Path $root 'gui-tools'),(Get-Content (Join-Path $RunDir 'request.json') -Raw)))|ConvertFrom-Json}
 $results=@()
 $caseIndex=0
 foreach($case in $p.tests){
  $names=New-Object 'System.Collections.Generic.List[string]';$values=New-Object 'System.Collections.Generic.List[object]';$types=New-Object 'System.Collections.Generic.List[string]'
  foreach($prop in $case.inputs.PSObject.Properties){$names.Add($prop.Name);$values.Add($prop.Value);$t=$p.input_types.($prop.Name);if(!$t){$t=if($prop.Value -is [bool]){'bool'}else{'double'}};$types.Add([string]$t)}
  $outputNames=New-Object 'System.Collections.Generic.List[string]'
  foreach($prop in $case.expected.PSObject.Properties){$outputNames.Add($prop.Name)}
  if($p.runtime_checks){foreach($prop in $p.runtime_checks.PSObject.Properties){$outputNames.Add($prop.Name)}}
  $gui=$null
  if($p.gui_buttons){$gui=([GuiWorker]::RunCaseJson((Join-Path $RunDir $p.filename),(Join-Path $root 'gui-tools'),(Get-Content (Join-Path $RunDir 'request.json') -Raw),$caseIndex))|ConvertFrom-Json;$actual=$gui.actual}
  else {$actual=([GenericWorker]::RunCaseJson((Join-Path $RunDir $p.filename),$names.ToArray(),$values.ToArray(),$types.ToArray(),$outputNames.ToArray()))|ConvertFrom-Json}
  $caseIndex++
  foreach($prop in $case.expected.PSObject.Properties){Assert-Value $actual.($prop.Name) $prop.Value ([string]$p.output_types.($prop.Name)) $prop.Name}
  if($p.runtime_checks){foreach($prop in $p.runtime_checks.PSObject.Properties){$t=if($prop.Value -is [bool]){'bool'}else{'int32'};Assert-Value $actual.($prop.Name) $prop.Value $t $prop.Name}}
  $results+=@{inputs=$case.inputs;expected=$case.expected;actual=$actual;passed=$true;gui=$gui}
 }
 $compileAfter=$null;if($p.typedef_manifest){$compileAfter=([TypedefWorker]::ValidateJson($RunDir,(Join-Path $root 'gui-tools'),(Get-Content (Join-Path $RunDir 'request.json') -Raw)))|ConvertFrom-Json}
 $moduleHashes=@{};foreach($module in $p.module_files){$moduleHashes[$module]=(Get-FileHash (Join-Path (Join-Path $RunDir 'Modules') $module) -Algorithm SHA256).Hash}
 $typedefHashes=@{};if($p.typedef_manifest){foreach($t in $p.typedef_manifest.types.PSObject.Properties){$typedefHashes[$t.Value.file]=(Get-FileHash (Join-Path (Join-Path $RunDir 'Types') $t.Value.file) -Algorithm SHA256).Hash}}
 $record=@{compile_before=$compileBefore;compile_after=$compileAfter;typedef_sha256=$typedefHashes;module_sha256=$moduleHashes;ok=$true;task='vi_build';run_id=(Split-Path $RunDir -Leaf);cases=$results;artifact=(Join-Path $RunDir $p.filename);sha256=(Get-FileHash (Join-Path $RunDir $p.filename) -Algorithm SHA256).Hash;labview_version=[GenericWorker]::LastVersion;simulation_only=$true}
} catch {$record=@{ok=$false;error='LabVIEW validation failed';detail=$_.Exception.Message}}
$record|ConvertTo-Json -Depth 30 -Compress|Set-Content (Join-Path $RunDir 'result.json') -Encoding UTF8
