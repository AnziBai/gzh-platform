$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  $python = "python"
}

Start-Process -FilePath "cmd.exe" -ArgumentList @(
  "/k",
  "cd /d `"$backend`" && `"$python`" app.py"
) -WindowStyle Minimized

Start-Process -FilePath "cmd.exe" -ArgumentList @(
  "/k",
  "cd /d `"$frontend`" && npm run dev -- --host 127.0.0.1 --port 3001"
) -WindowStyle Minimized

Write-Host "Backend:  http://127.0.0.1:5001"
Write-Host "Frontend: http://127.0.0.1:3001"
