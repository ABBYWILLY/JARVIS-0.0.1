param(
    [string]$PythonExecutable = '',
    [switch]$RequireHardware
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne 'Windows_NT') { throw 'Build this standalone prototype on Windows.' }

function Check-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed: exit $LASTEXITCODE" }
}

# Quote individual argv entries for CreateProcess, including paths with spaces.
function ConvertTo-NativeArgument([string]$Value) {
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

if (-not $PythonExecutable) {
    $PythonExecutable = & py -3.12 -c 'import sys; print(sys.executable)'
    Check-Exit 'Locate Python 3.12'
}
& $PythonExecutable -c 'import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32'
Check-Exit 'Python 3.12 x64'
& $PythonExecutable -m venv .venv-build-gpu
Check-Exit 'Create isolated GPU build environment'
$Python = Join-Path $PWD '.venv-build-gpu\Scripts\python.exe'
& $Python -m pip install --disable-pip-version-check -r requirements-build.txt -r requirements-gpu.txt
Check-Exit 'Install pinned build and GPU dependencies'

$OutputDirectory = Join-Path $PWD 'dist\presence-gpu'
$Diagnostics = Join-Path $OutputDirectory 'diagnostics'
$Licenses = Join-Path $OutputDirectory 'licenses'
foreach ($Directory in @($Diagnostics, $Licenses)) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}

# Loading the native modules before probing distinguishes broken packaging or
# missing DLLs from a runner whose display driver has no OpenGL 3.3 support.
# This does not create a visible window, start audio, or fetch any model.
$DependencyInventory = @'
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import moderngl
import moderngl.mgl
import _moderngl
import glcontext
import glcontext.wgl
import glfw

output = Path(sys.argv[1])
inventory = {'python': sys.version, 'platform': platform.platform(), 'packages': {}}
for name in ('moderngl', 'glcontext', 'glfw'):
    dist = metadata.distribution(name)
    destination = output / 'licenses' / name
    destination.mkdir(parents=True, exist_ok=True)
    native = []
    licenses = []
    for entry in dist.files or ():
        path = Path(dist.locate_file(entry))
        lower = path.name.lower()
        if path.suffix.lower() in ('.pyd', '.dll'):
            native.append({'path': str(entry), 'size_bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if '.dist-info/' in str(entry).replace('\\', '/') and (
                lower in ('metadata', 'wheel') or any(word in lower for word in ('license', 'copying', 'notice'))):
            relative = Path(*Path(entry).parts[1:])
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            if any(word in lower for word in ('license', 'copying', 'notice')):
                licenses.append(str(relative))
    if not native or not licenses:
        raise RuntimeError(f'{name}: native binaries or distribution license missing')
    inventory['packages'][name] = {'version': dist.version, 'license': dist.metadata.get('License'),
                                    'native_binaries': native, 'license_files': licenses}
inventory['glfw_native_version'] = list(glfw.get_version())
inventory['glfw_native_version_string'] = glfw.get_version_string().decode('utf-8', errors='replace')

# The wheel's MIT license covers the Python wrapper. Its bundled glfw3.dll
# additionally carries GLFW's upstream zlib/libpng license, reproduced here.
native_license = '''GLFW native library (glfw3.dll)
https://www.glfw.org/license.html

Copyright (c) 2002-2006 Marcus Geelnard
Copyright (c) 2006-2019 Camilla L\u00f6wy

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would
   be appreciated but is not required.

2. Altered source versions must be plainly marked as such, and must not
   be misrepresented as being the original software.

3. This notice may not be removed or altered from any source
   distribution.
'''
(output / 'licenses' / 'GLFW-NATIVE-LICENSE.txt').write_text(native_license, encoding='utf-8')
(output / 'licenses' / 'THIRD-PARTY-NOTICES.txt').write_text(
    'Optional standalone GPU prototype. No voice dependencies or model weights are included.\n'
    'See the moderngl, glcontext and glfw distribution metadata and license files in this directory.\n'
    'glfw metadata covers the Python wrapper; GLFW-NATIVE-LICENSE.txt covers the bundled GLFW library.\n',
    encoding='utf-8')
(output / 'diagnostics' / 'dependency-inventory.json').write_text(
    json.dumps(inventory, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
'@
& $Python -c $DependencyInventory $OutputDirectory
Check-Exit 'GPU native imports, dependency metadata and license inventory'

function Invoke-GpuProbe([string]$Label, [string]$Executable, [string[]]$PrefixArguments) {
    $Temporary = Join-Path ([IO.Path]::GetTempPath()) ('jarvis-gpu-probe-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $Temporary | Out-Null
    $ReportPath = Join-Path $Temporary 'probe.json'
    $SavedReport = Join-Path $Diagnostics "$Label-probe.json"
    $Arguments = @()
    foreach ($Argument in $PrefixArguments) { $Arguments += $Argument }
    $Arguments += @('--probe', '--report', $ReportPath)
    if ($RequireHardware) { $Arguments += '--require-hardware' }
    $CommandLine = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        # ReportPath is new for every invocation; a stale report can never pass.
        $Process = Start-Process -FilePath $Executable -ArgumentList $CommandLine -PassThru `
            -RedirectStandardOutput (Join-Path $Diagnostics "$Label-stdout.txt") `
            -RedirectStandardError (Join-Path $Diagnostics "$Label-stderr.txt")
        $null = $Process.Handle
        if (-not $Process.WaitForExit(60000)) {
            & taskkill.exe /PID $Process.Id /T /F | Out-Null
            throw "$Label probe exceeded 60 seconds (process tree terminated)."
        }
        $Process.WaitForExit()
        $Timer.Stop()
        $ExitCode = $Process.ExitCode
        if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) {
            throw "$Label probe exited $ExitCode without its new JSON report."
        }
        Copy-Item -LiteralPath $ReportPath -Destination $SavedReport -Force
        $Report = Get-Content -LiteralPath $SavedReport -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($Report.shutdown -ne 'complete') { throw "$Label probe did not complete cleanup: $SavedReport" }
        if ($ExitCode -eq 0 -and $Report.status -eq 'supported' -and $Report.shader_compile_and_frame -eq $true) {
            if ($RequireHardware -and $Report.renderer.acceleration -ne 'hardware_reported') {
                throw "$Label probe did not report hardware acceleration: $SavedReport"
            }
            $Outcome = 'shader_compile_and_real_frame_passed'
        } else {
            # Only explicit GLFW WGL diagnostics for an absent/insufficient
            # driver are allowed on hosted Windows runners. Import failures,
            # missing DLLs, shader exceptions and all unknown failures are fatal.
            $DriverAbsent = $Report.status -eq 'unsupported' -and $Report.unavailable_reason -eq 'context' -and $Report.error -match (
                '^GpuUnavailable: OpenGL.*WGL: (The driver does not appear to support OpenGL|' +
                'Driver does not support OpenGL version 3\.3|' +
                'OpenGL version 3\.3 requested but WGL_ARB_create_context is unavailable|' +
                'OpenGL profile requested but WGL_ARB_create_context_profile is unavailable)')
            if ($RequireHardware -or $ExitCode -ne 2 -or -not $DriverAbsent) {
                throw "$Label probe failed unexpectedly (exit $ExitCode): $SavedReport"
            }
            $Outcome = 'driver_unavailable_explicitly_reported'
            Write-Warning "$Label probe: OpenGL 3.3 driver unavailable; no shader/hardware validation claimed."
        }
        return [pscustomobject]@{
            exit_code = $ExitCode
            status = $Report.status
            outcome = $Outcome
            parent_wall_seconds = $Timer.Elapsed.TotalSeconds
            report = "diagnostics/$Label-probe.json"
        }
    } finally {
        $Timer.Stop()
        if (Test-Path -LiteralPath $Temporary) { Remove-Item -LiteralPath $Temporary -Recurse -Force }
    }
}

$SourceProbe = Invoke-GpuProbe 'source' $Python @((Join-Path $PWD 'run_presence_gpu.py'))
$BuildArguments = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--noupx',
    '--name', 'JarvisPresenceGPU', '--distpath', $OutputDirectory,
    '--workpath', 'build\presence-gpu', '--specpath', 'build\presence-gpu',
    '--hidden-import', 'moderngl.mgl', '--hidden-import', '_moderngl',
    '--hidden-import', 'glcontext.wgl'
)
foreach ($Package in @('moderngl', 'glcontext', 'glfw')) {
    # Includes glfw3.dll and its bundled native runtime as well as extension .pyds.
    $BuildArguments += @('--collect-all', $Package, '--copy-metadata', $Package)
}
# The shared signal_view helper imports no audio backend. Exclude the optional
# voice stack explicitly even when rebuilding in a previously used environment.
foreach ($Package in @('numpy', 'sounddevice', 'soxr', 'faster_whisper', 'piper',
        'ctranslate2', 'onnxruntime', 'torch', 'transformers', 'huggingface_hub', 'tokenizers')) {
    $BuildArguments += @('--exclude-module', $Package)
}
$BuildArguments += 'run_presence_gpu.py'
& $Python @BuildArguments
Check-Exit 'Build JarvisPresenceGPU.exe'
$ExePath = Join-Path $OutputDirectory 'JarvisPresenceGPU.exe'
$FrozenProbe = Invoke-GpuProbe 'exe' $ExePath @()
if ($SourceProbe.status -eq 'supported' -and $FrozenProbe.status -ne 'supported') {
    throw 'Source OpenGL probe passed but frozen executable did not; packaging regression.'
}
$Hash = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  JarvisPresenceGPU.exe" | Set-Content -Encoding ascii (Join-Path $OutputDirectory 'JarvisPresenceGPU.exe.sha256')
$BuildReport = [ordered]@{
    schema_version = 1
    artifact = 'JarvisPresenceGPU.exe'
    package_size_bytes = (Get-Item -LiteralPath $ExePath).Length
    sha256 = $Hash
    require_hardware = [bool]$RequireHardware
    source_probe = $SourceProbe
    executable_probe = $FrozenProbe
    startup_exe_parent_wall_seconds = $FrozenProbe.parent_wall_seconds
    startup_measurement_scope = 'Parent launch through process exit; includes onefile extraction, imports, shader/frame probe and cleanup. Not time to first visible frame.'
    application_integrated = $false
    hardware_validation = 'pending'
    rtx_3070_validation = 'not_measured'
    ollama_and_live_voice_coexecution = 'not_measured'
}
[IO.File]::WriteAllText((Join-Path $Diagnostics 'build-report.json'),
    ($BuildReport | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Host 'Standalone unsigned GPU prototype built: dist\presence-gpu\JarvisPresenceGPU.exe'
Write-Host 'This build does not validate RTX performance or concurrent Ollama/live voice.'
