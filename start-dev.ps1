param(
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$requirements = Join-Path $backend "requirements.txt"
$backendStamp = Join-Path $backend ".venv\.deps-stamp"
$frontendStamp = Join-Path $frontend "node_modules\.deps-stamp"

function Test-CommandExists($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Find-Python {
  $candidates = @(
    @{ File = "py"; Args = @("-3") },
    @{ File = "python"; Args = @() },
    @{ File = "python3"; Args = @() }
  )

  foreach ($candidate in $candidates) {
    if (-not (Test-CommandExists $candidate.File)) {
      continue
    }

    $probe = @"
import sys
exe = sys.executable
if sys.version_info < (3, 10) or "WindowsApps" in exe:
    raise SystemExit(1)
print(exe)
"@
    try {
      $output = & $candidate.File @($candidate.Args) -c $probe 2>$null
      if ($LASTEXITCODE -eq 0 -and $output) {
        return $candidate
      }
    } catch {
      continue
    }
  }

  throw "Python 3.10+ was not found. Install Python and enable Add python.exe to PATH."
}

function Ensure-Backend {
  if ((Test-Path $venvPython) -and $SkipInstall) {
    return
  }

  if (-not (Test-Path $venvPython)) {
    Write-Host "Creating backend virtual environment..."
    $python = Find-Python
    & $python.File @($python.Args) -m venv (Join-Path $backend ".venv")
  }

  if ($SkipInstall) {
    return
  }

  $shouldInstall = -not (Test-Path $backendStamp)
  if ((Test-Path $backendStamp) -and (Test-Path $requirements)) {
    $shouldInstall = (Get-Item $requirements).LastWriteTimeUtc -gt (Get-Item $backendStamp).LastWriteTimeUtc
  }

  if ($shouldInstall) {
    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install -r $requirements
    New-Item -ItemType File -Force -Path $backendStamp | Out-Null
  }
}

function Ensure-Frontend {
  if (-not (Test-CommandExists "node")) {
    throw "Node.js was not found. Install Node.js LTS and reopen PowerShell."
  }
  if (-not (Test-CommandExists "npm")) {
    throw "npm was not found. Confirm Node.js is installed correctly."
  }

  if ($SkipInstall) {
    return
  }

  $nodeModules = Join-Path $frontend "node_modules"
  $packageLock = Join-Path $frontend "package-lock.json"
  $shouldInstall = -not (Test-Path $nodeModules) -or -not (Test-Path $frontendStamp)
  if ((Test-Path $frontendStamp) -and (Test-Path $packageLock)) {
    $shouldInstall = $shouldInstall -or ((Get-Item $packageLock).LastWriteTimeUtc -gt (Get-Item $frontendStamp).LastWriteTimeUtc)
  }

  if ($shouldInstall) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontend
    try {
      npm install
      New-Item -ItemType File -Force -Path $frontendStamp | Out-Null
    } finally {
      Pop-Location
    }
  }
}

Ensure-Backend
Ensure-Frontend

$backendCommand = "cd /d `"$backend`" && `"$venvPython`" app.py"
$frontendCommand = "cd /d `"$frontend`" && npm run dev -- --host 127.0.0.1 --port 3001"

Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $backendCommand) -WindowStyle Minimized
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $frontendCommand) -WindowStyle Minimized

Write-Host ""
Write-Host "System started:"
Write-Host "Backend:  http://127.0.0.1:5001"
Write-Host "Frontend: http://127.0.0.1:3001"
Write-Host ""
Write-Host "First run: open the frontend, go to Settings, and complete the bootstrap wizard."
