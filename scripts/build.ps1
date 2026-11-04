param(
    [string]$Python = 'python',
    [string]$BundledTools = '',
    [switch]$OneFile
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$projectRoot = (Get-Location).Path
if ($BundledTools) { $env:PYTHONPATH = $BundledTools }
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot '.build/pyinstaller-cache'
# Prevent unrelated tools (notably Poppler's ICU) from being bundled in place
# of the Windows ICU used by Qt. These DLLs are found through PATH at build time.
$pythonExecutable = (Get-Command $Python -ErrorAction Stop).Source
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$(Split-Path -Parent $pythonExecutable)"
$mode = if ($OneFile) { '--onefile' } else { '--onedir' }
& $Python -m PyInstaller --noconfirm $mode --windowed --name '归档' --icon (Join-Path $projectRoot 'assets/app.ico') --add-data "$projectRoot/assets;assets" --add-data "$projectRoot/scripts/office.ps1;scripts" --hidden-import 'lxml._elementpath' --exclude-module 'PySide6.QtWebEngineWidgets' --exclude-module 'PySide6.QtWebEngineCore' --exclude-module 'PySide6.QtQml' --exclude-module 'PySide6.QtQuick' --exclude-module 'PySide6.QtNetwork' --distpath 'release-native' --workpath '.build/freeze-native' --specpath '.build' 'main.py'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$releaseFormat = if ($OneFile) { 'singlefile' } else { 'directory' }
& $Python 'scripts/package_release.py' --format $releaseFormat
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
Write-Output 'Native desktop build complete: release-native'
