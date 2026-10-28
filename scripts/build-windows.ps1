param(
    [string]$PythonExecutable = '',
    [switch]$WithVoice,
    [switch]$WithGpu
)
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
$BuildEnvironment = if ($WithVoice) { '.venv-build-voice' } else { '.venv-build' }
if ($WithGpu) { $BuildEnvironment += '-gpu' }
& $PythonExecutable -m venv $BuildEnvironment
Check-Exit 'Création environnement Python 3.12'
$Python = Join-Path $PWD "$BuildEnvironment\Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check -r requirements-build.txt
Check-Exit 'Installation des outils de compilation'
if ($WithGpu) {
    & $Python -m pip install --disable-pip-version-check -r requirements-gpu.txt
    Check-Exit 'Installation des composants holographiques facultatifs'
    & $Python -c 'import moderngl, moderngl.mgl, _moderngl, glcontext, glcontext.wgl, glfw; from PIL import Image, ImageFont'
    Check-Exit 'Imports GPU natifs et rendu des sous-titres'
}
if ($WithVoice) {
    & $Python -m pip install --disable-pip-version-check -r requirements-voice.txt
    Check-Exit 'Installation des composants vocaux épinglés'
    # Fail before the test suite if optional imports would silently skip audio tests.
    # Silero is shipped by faster-whisper; this loads no STT/TTS model or device.
    $VoiceCheck = @'
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import numpy, sounddevice, soxr, faster_whisper, piper, ctranslate2, onnxruntime
onnxruntime.disable_telemetry_events()
from jarvis.audio import FRAME, SileroFrames
probability = SileroFrames().probability([0.0] * FRAME)
assert 0 <= probability < 0.6, probability
import tkinter as tk
root = tk.Tk()
root.withdraw()
root.update()
root.destroy()
'@
    & $Python -c $VoiceCheck
    Check-Exit 'Imports natifs, Silero embarqué et affichage Tk'
}
# One full regression pass, including the audio/Presence contracts when installed.
# Surface failing tracebacks in the public run annotations as well as the log.
# Detailed job logs can require authentication even for this public repository.
$TestRunner = @'
import sys
import unittest

suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
for test, traceback in result.errors + result.failures:
    # Workflow-command escaping, independent of the Windows console code page.
    detail = f'{test.id()}\n{traceback}'.encode('ascii', 'backslashreplace').decode('ascii')[:12000]
    detail = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print(f'::error title=Windows regression::{detail}', flush=True)
sys.exit(not result.wasSuccessful())
'@
& $Python -c $TestRunner
Check-Exit 'Tests'
$BuildArguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', 'Jarvis', '--noupx', '--distpath', 'dist\jalon-2',
    '--workpath', 'build\jalon-2', '--specpath', 'build\jalon-2'
)
if ($WithVoice) {
    foreach ($Package in @('piper', 'faster_whisper', 'ctranslate2', 'onnxruntime', 'sounddevice', 'soxr')) {
        $BuildArguments += @('--collect-all', $Package)
    }
    # NumPy and sounddevice hooks collect native libraries, including PortAudio DLLs.
}
if ($WithGpu) {
    foreach ($Package in @('moderngl', 'glcontext', 'glfw', 'PIL')) {
        $BuildArguments += @('--collect-all', $Package)
    }
    foreach ($Package in @('moderngl', 'glcontext', 'glfw', 'Pillow')) {
        $BuildArguments += @('--copy-metadata', $Package)
    }
    $BuildArguments += @('--hidden-import', 'moderngl.mgl', '--hidden-import', '_moderngl', '--hidden-import', 'glcontext.wgl')
}
$BuildArguments += 'run.py'
& $Python @BuildArguments
Check-Exit 'Compilation Jarvis.exe'

# Preserve any earlier dist\Jarvis.exe; Jalon 2 always has its own output directory.
$ExePath = Join-Path $PWD 'dist\jalon-2\Jarvis.exe'
function ConvertTo-NativeArgument([string]$Value) {
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}
function Invoke-ExeSmoke([string]$Argument, [string]$Executable = $ExePath,
                         [string[]]$PrefixArguments = @(), [string]$Label = 'exe') {
    # Every frozen-process check gets its own database, never the user's profile.
    $PreviousData = $env:JARVIS_DATA_DIR
    $SmokeData = Join-Path ([IO.Path]::GetTempPath()) ('jarvis-smoke-' + [guid]::NewGuid())
    try {
        $env:JARVIS_DATA_DIR = $SmokeData
        $Arguments = @($PrefixArguments) + @($Argument)
        $CommandLine = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
        $Exe = Start-Process -FilePath $Executable -ArgumentList $CommandLine -PassThru
        $null = $Exe.Handle
        if (-not $Exe.WaitForExit(60000)) {
            # One-file PyInstaller starts child processes; stop the whole test tree.
            & taskkill.exe /PID $Exe.Id /T /F | Out-Null
            throw "Jarvis.exe $Argument dépasse le délai de 60 secondes."
        }
        $Exe.WaitForExit()
        $GpuReport = Join-Path $SmokeData 'gpu-smoke.json'
        if (Test-Path $GpuReport) {
            New-Item -ItemType Directory -Path 'dist\jalon-2\diagnostics' -Force | Out-Null
            Copy-Item -LiteralPath $GpuReport -Destination "dist\jalon-2\diagnostics\$Label-gpu-smoke.json"
        }
        if ($Exe.ExitCode -ne 0) { throw "Test Jarvis.exe $Argument en échec : $($Exe.ExitCode)" }
        if (-not (Test-Path (Join-Path $SmokeData 'jarvis.sqlite3'))) { throw 'Base de données du test absente.' }
    } finally {
        $env:JARVIS_DATA_DIR = $PreviousData
        if (Test-Path $SmokeData) { Remove-Item -Recurse -Force $SmokeData }
    }
}

# Covers Tk/SQLite and the existing frozen multiprocessing boundary without Ollama.
Invoke-ExeSmoke '--smoke-test'
if ($WithVoice) {
    # Adds native audio imports and packaged Silero ONNX through the frozen worker.
    Invoke-ExeSmoke '--voice-smoke-test'
}
if ($WithGpu) {
    # Both probes use the same spawned renderer as the app, including its HUD.
    # A specifically identified missing driver is recorded, never called a frame.
    Invoke-ExeSmoke -Argument '--gpu-smoke-test' -Executable $Python -PrefixArguments @('run.py') -Label 'source'
    Invoke-ExeSmoke '--gpu-smoke-test'
    $SourceGpu = Get-Content 'dist\jalon-2\diagnostics\source-gpu-smoke.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $FrozenGpu = Get-Content 'dist\jalon-2\diagnostics\exe-gpu-smoke.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($SourceGpu.status -eq 'supported' -and $FrozenGpu.status -ne 'supported') {
        throw 'GPU disponible dans les sources mais indisponible dans Jarvis.exe : régression de compilation.'
    }
}
Get-FileHash $ExePath -Algorithm SHA256 | ForEach-Object {
    "$($_.Hash.ToLower())  Jarvis.exe" | Set-Content -Encoding ascii 'dist\jalon-2\Jarvis.exe.sha256'
}
Write-Host 'Compilation et tests de démarrage terminés : dist\jalon-2\Jarvis.exe (non signé).'
