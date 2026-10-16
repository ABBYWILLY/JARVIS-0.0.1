param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne 'Windows_NT') { throw 'Compiler sur Windows 11 ou sur le runner GitHub Windows.' }

function Check-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step : code $LASTEXITCODE" }
}

if (-not $PythonExecutable) {
    $PythonExecutable = & py -3.12 -c 'import sys; print(sys.executable)'
    Check-Exit 'Localisation Python 3.12'
}
& $PythonExecutable -c 'import sys; assert sys.version_info[:2] == (3, 12)'
Check-Exit 'Version Python'
& $PythonExecutable -m venv .venv-build
Check-Exit 'Création environnement Python 3.12'
$Python = Join-Path $PWD '.venv-build\Scripts\python.exe'
& $Python -m pip install --disable-pip-version-check -r requirements-build.txt
Check-Exit 'Installation des outils de compilation'
& $Python -m unittest discover -s tests -v
Check-Exit 'Tests'
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name Jarvis --noupx run.py
Check-Exit 'Compilation Jarvis.exe'

# Isolate smoke-test data from the real user's conversations.
$PreviousData = $env:JARVIS_DATA_DIR
$SmokeData = Join-Path ([IO.Path]::GetTempPath()) ('jarvis-smoke-' + [guid]::NewGuid())
try {
    $env:JARVIS_DATA_DIR = $SmokeData
    $Exe = Start-Process -FilePath (Join-Path $PWD 'dist\Jarvis.exe') -ArgumentList '--smoke-test' -PassThru
    if (-not $Exe.WaitForExit(30000)) {
        $Exe.Kill()
        throw 'Jarvis.exe ne termine pas son test de démarrage dans les 30 secondes.'
    }
    if ($Exe.ExitCode -ne 0) { throw "Test Jarvis.exe en échec : $($Exe.ExitCode)" }
    if (-not (Test-Path (Join-Path $SmokeData 'jarvis.sqlite3'))) { throw 'Base de données du test absente.' }
} finally {
    $env:JARVIS_DATA_DIR = $PreviousData
    if (Test-Path $SmokeData) { Remove-Item -Recurse -Force $SmokeData }
}
Get-FileHash 'dist\Jarvis.exe' -Algorithm SHA256 | ForEach-Object {
    "$($_.Hash.ToLower())  Jarvis.exe" | Set-Content -Encoding ascii 'dist\Jarvis.exe.sha256'
}
Write-Host 'Compilation et test de démarrage terminés : dist\Jarvis.exe (non signé).'
