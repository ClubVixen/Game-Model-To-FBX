param([Parameter(Mandatory=$true)][string]$GamePath)
$ErrorActionPreference='Stop'
$managed=Join-Path $GamePath 'CharaStudio_Data\Managed'
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v3.5\csc.exe'
$references=@(
    (Join-Path $managed 'UnityEngine.dll'),
    (Join-Path $managed 'Assembly-CSharp.dll'),
    (Join-Path $GamePath 'BepInEx\core\BepInEx.dll'),
    (Join-Path $GamePath 'BepInEx\plugins\KKAPI.dll')
)
$arguments=@('/nologo','/target:library',"/out:$PSScriptRoot\StudioFbxBridge.dll")
foreach($reference in $references) {
    if(-not (Test-Path -LiteralPath $reference)){throw "Missing dependency: $reference"}
    $arguments += "/reference:$reference"
}
& $compiler @arguments (Join-Path $PSScriptRoot 'StudioFbxBridge.cs')
if($LASTEXITCODE -ne 0){throw 'Studio exporter compilation failed'}
Write-Output "Built $PSScriptRoot\StudioFbxBridge.dll"
