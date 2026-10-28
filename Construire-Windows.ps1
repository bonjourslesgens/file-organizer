param([switch]$Installer, [switch]$SkipSourceTests)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m venv .venv-build
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ est requis pour la construction seulement.' }
$python = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
& $python -m pip install . 'pyinstaller==6.16.0'
if ($LASTEXITCODE -ne 0) { throw 'Installation de PyInstaller impossible.' }
if (-not $SkipSourceTests) {
    & $python -m tests.ci_runner
    if ($LASTEXITCODE -ne 0) { throw 'Les tests ont echoue. Aucun executable ne sera construit.' }
} # CI uses this option only after the identical commit passed its Linux/Windows matrix.
$version = & $python -c 'from file_organizer import __version__; print(__version__)'
& $python -m PyInstaller --noconfirm --clean --onefile --name FileOrganizer --version-file windows/version_info.txt --add-data 'file_organizer/static;file_organizer/static' launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Construction impossible.' }
& $python -m tests.binary_smoke --exe dist/FileOrganizer.exe
if ($LASTEXITCODE -ne 0) { throw 'Verification du binaire impossible.' }
'Executable teste sans Python dans PATH.' | Set-Content dist/PORTABLE_VALIDATED.txt
$exeHash = Get-FileHash dist/FileOrganizer.exe -Algorithm SHA256
"$($exeHash.Hash.ToLower())  FileOrganizer.exe" | Set-Content dist/SHA256SUMS.txt -Encoding ascii
Write-Host '::notice title=Portable Windows valide::FileOrganizer.exe construit et teste ; copie, Corbeille et redemarrage verifies.'
if ($Installer) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $compiler = if ($iscc) { $iscc.Source } else { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    if (-not (Test-Path $compiler)) { throw 'Inno Setup 6 est requis pour fabriquer un installateur.' }
    & $compiler "/DAppVersion=$version" windows/FileOrganizer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Construction de l installateur impossible.' }
}
Get-ChildItem dist/*.exe | ForEach-Object {
    $hash = Get-FileHash $_.FullName -Algorithm SHA256
    "$($hash.Hash.ToLower())  $($_.Name)"
} | Set-Content -Path dist/SHA256SUMS.txt -Encoding ascii
Write-Host 'Construction et verification terminees. Artefacts dans dist. Aucune publication automatique.'
