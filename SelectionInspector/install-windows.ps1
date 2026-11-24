# PowerShell installer for Windows. Copies this add-in into Fusion's AddIns folder.
$AddinName = "SelectionInspector"

$ErrorActionPreference = "Stop"

$SrcDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$DestRoot = Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns"
$DestDir  = Join-Path $DestRoot $AddinName

Write-Host "Installing $AddinName ..."
Write-Host "  from: $SrcDir"
Write-Host "  to:   $DestDir"

if (-not (Test-Path $DestRoot)) {
    Write-Host "AddIns folder not found. Is Fusion installed for this user?" -ForegroundColor Yellow
    Write-Host "Expected: $DestRoot"
    Read-Host "Press Enter to close"
    exit 1
}

if ((Resolve-Path $SrcDir).Path -eq $DestDir) {
    Write-Host "This copy is already in Fusion's AddIns folder; nothing to do."
    Read-Host "Press Enter to close"
    exit 0
}

if (Test-Path $DestDir) { Remove-Item $DestDir -Recurse -Force }
New-Item -ItemType Directory -Path $DestDir | Out-Null

$exclude = @("install-windows.ps1", "install-windows.cmd", "install-macos.command", "READ ME FIRST.txt", "README.txt", "__pycache__", ".DS_Store")
Get-ChildItem -Path $SrcDir -Force | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
    Copy-Item $_.FullName -Destination $DestDir -Recurse -Force
}
# The filter above only sees the top level; remove caches from subfolders too.
Get-ChildItem -Path $DestDir -Recurse -Force -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $DestDir -Recurse -Force -File -Filter ".DS_Store" | Remove-Item -Force

Write-Host ""
Write-Host "Done. In Fusion: Utilities > Add-Ins > Scripts and Add-Ins (Shift+S)," -ForegroundColor Green
Write-Host "select `"$AddinName`" under Add-Ins, and turn on Run and Run on Startup."
Write-Host ""
Write-Host "The Selection Inspector button is in the INSPECT panel of every tab."
Write-Host "The version shown in Scripts and Add-Ins only catches up after Fusion restarts;"
Write-Host "the palette title shows the version actually running."
Write-Host "Your keyboard shortcut and settings are kept across reinstalls."
Read-Host "Press Enter to close"
