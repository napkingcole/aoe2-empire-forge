# Wraps the one-folder Store build (EF_STORE=1 pyinstaller) into an MSIX.
#
#   $env:EF_STORE = "1"; pyinstaller aoe2civbuilder.spec --noconfirm
#   pwsh packaging/msix/build_msix.ps1
#
# Produces dist/AOE2EmpireForge-<version>.msix, UNSIGNED: Partner Center signs
# Store submissions itself.  For a local test install without signing, use the
# layout instead (Developer Mode on):  Add-AppxPackage -Register dist\msix-layout\AppxManifest.xml
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."

# version.py's "2.5.1" -> "2.5.1.0": MSIX wants four parts, and the Store
# reserves the fourth, which must stay 0.
$verLine = Select-String -Path "$root\version.py" -Pattern '__version__\s*=\s*"([^"]+)"'
$ver = $verLine.Matches[0].Groups[1].Value
$parts = @($ver.Split('.') | ForEach-Object { [int]($_ -replace '\D.*$', '') })
while ($parts.Count -lt 3) { $parts += 0 }
$msixVer = "{0}.{1}.{2}.0" -f $parts[0], $parts[1], $parts[2]

$bundle = "$root\dist\AOE2EmpireForge"
if (-not (Test-Path "$bundle\AOE2EmpireForge.exe")) {
    throw "No one-folder build at $bundle - run pyinstaller with EF_STORE=1 first"
}

$layout = "$root\dist\msix-layout"
if (Test-Path $layout) { Remove-Item -Recurse -Force $layout }
New-Item -ItemType Directory -Path $layout | Out-Null
Copy-Item -Recurse $bundle "$layout\AOE2EmpireForge"
Copy-Item -Recurse "$PSScriptRoot\Assets" "$layout\Assets"
(Get-Content -Raw -Encoding utf8 "$PSScriptRoot\AppxManifest.xml") -replace '__VERSION__', $msixVer |
    Set-Content -Encoding utf8 "$layout\AppxManifest.xml"

# makeappx ships with the Windows SDK (present on GitHub's windows-latest).
$makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $makeappx) { throw "makeappx.exe not found - install the Windows SDK" }

$out = "$root\dist\AOE2EmpireForge-$msixVer.msix"
& $makeappx.FullName pack /d $layout /p $out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx failed ($LASTEXITCODE)" }
Write-Host "Built $out"
