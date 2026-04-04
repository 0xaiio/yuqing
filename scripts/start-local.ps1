param(
    [switch]$SkipInstall,
    [switch]$WithTauri
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$backendEnv = Join-Path $repoRoot "backend\.env"
$backendEnvExample = Join-Path $repoRoot "backend\.env.example"
$rustBin = Join-Path $env:USERPROFILE ".cargo\bin"
$buildToolsGuide = Join-Path $repoRoot "docs\windows-build-tools.md"

function Add-PathEntryIfMissing {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Entry
    )

    if (-not (Test-Path $Entry)) {
        return $false
    }

    $pathEntries = ($env:Path -split ";") | Where-Object { $_ }
    if ($pathEntries -contains $Entry) {
        return $true
    }

    $env:Path = "$Entry;$env:Path"
    return $true
}

function Test-MsvcBuildTools {
    if (Get-Command cl.exe -ErrorAction SilentlyContinue) {
        return $true
    }

    $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        return $false
    }

    $installPath = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        return $false
    }

    $clPath = Get-ChildItem -Path $installPath -Filter cl.exe -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $clPath) {
        return $false
    }

    $clDir = Split-Path $clPath -Parent
    Add-PathEntryIfMissing $clDir | Out-Null
    return $true
}

function Get-PythonBootstrapCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3.12")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3.12 was not found."
}

Set-Location $repoRoot

$rustReady = Add-PathEntryIfMissing $rustBin
if ($rustReady) {
    Write-Host "Rust toolchain path ready: $rustBin"
} else {
    Write-Warning "Rust toolchain path was not found at $rustBin"
}

if (-not (Test-Path $venvPython)) {
    $pythonBootstrap = Get-PythonBootstrapCommand
    Write-Host "Creating .venv..."
    if ($pythonBootstrap.Length -gt 1) {
        & $pythonBootstrap[0] $pythonBootstrap[1] -m venv ".venv"
    } else {
        & $pythonBootstrap[0] -m venv ".venv"
    }
}

if (-not (Test-Path $backendEnv) -and (Test-Path $backendEnvExample)) {
    Write-Host "Copying backend/.env.example to backend/.env"
    Copy-Item $backendEnvExample $backendEnv
}

$msvcReady = Test-MsvcBuildTools
if ($WithTauri -and -not $rustReady) {
    throw "Tauri startup requires rustc/cargo on PATH. Expected Rust at $rustBin."
}

if ($WithTauri -and -not $msvcReady) {
    throw "Tauri startup requires Windows Visual Studio Build Tools. See $buildToolsGuide"
}

if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install -r "backend\requirements.txt"

    Write-Host "Installing frontend dependencies..."
    Push-Location (Join-Path $repoRoot "frontend")
    try {
        npm.cmd install
    } finally {
        Pop-Location
    }
}

$backendCommand = @"
Set-Location '$repoRoot'
`$env:PYTHONPATH = 'backend'
`$env:Path = '$env:Path'
& '$venvPython' -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
"@

if ($WithTauri) {
    $frontendCommand = @"
Set-Location '$repoRoot\frontend'
`$env:Path = '$env:Path'
npm.cmd run tauri:dev
"@
} else {
    $frontendCommand = @"
Set-Location '$repoRoot\frontend'
`$env:Path = '$env:Path'
npm.cmd run dev -- --host 127.0.0.1 --port 5173
"@
}

Write-Host "Starting backend window..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $backendCommand
)

Write-Host "Starting frontend window..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $frontendCommand
)

Start-Sleep -Seconds 3

if (-not $WithTauri) {
    Start-Process "http://127.0.0.1:5173"
}
Start-Process "http://127.0.0.1:8000/docs"

Write-Host ""
Write-Host "Local dev environment started."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend docs: http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "Optional flags:"
Write-Host "  -SkipInstall  Skip pip / npm install"
Write-Host "  -WithTauri    Start the Tauri shell instead of Vite"
