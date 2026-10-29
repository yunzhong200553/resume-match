param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$frontend = Join-Path $root 'frontend'
$url = 'http://127.0.0.1:8000'
$startedProcess = $null

function Test-Application {
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
        $homepageResponse = Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2
        return $health.data.service -eq 'resume-match' -and $homepageResponse.Content.Contains('ResumeMatch')
    } catch [System.Net.WebException] {
        return $false
    }
}

try {
    Set-Location -LiteralPath $root
    if (-not (Test-Path -LiteralPath $python)) {
        $bootstrap = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($bootstrap) {
            & $bootstrap.Source -3 -m venv .venv
        } else {
            $bootstrap = Get-Command python.exe -ErrorAction Stop
            & $bootstrap.Source -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python virtual environment.' }
    }

    & $python -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(name) is not None for name in ('fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'pydantic_settings', 'httpx', 'fitz', 'docx', 'reportlab', 'multipart')) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Restoring missing backend dependencies...'
        & $python -m pip install -r (Join-Path $root 'backend\requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    }

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { throw 'Node.js with npm is required. Install Node.js 20.19+ or 22.12+ and retry.' }
    Set-Location -LiteralPath $frontend
    if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules\.bin\vite.cmd')) -or
        -not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules\.bin\tsc.cmd'))) {
        Write-Host 'Restoring missing frontend dependencies...'
        if (Test-Path -LiteralPath (Join-Path $frontend 'package-lock.json')) { & $npm.Source ci }
        else { & $npm.Source install }
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    }
    Write-Host 'Building the application...'
    & $npm.Source run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    Set-Location -LiteralPath $root

    if (-not (Test-Application)) {
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { throw 'Port 8000 is occupied by a service that is not the complete ResumeMatch application. Close that service and retry; no process was terminated.' }
        Write-Host 'Starting the local application server...'
        $backend = Join-Path $root 'backend'
        $startedProcess = Start-Process -FilePath $python -ArgumentList "-m uvicorn app.main:app --app-dir `"$backend`" --host 127.0.0.1 --port 8000" -WorkingDirectory $root -NoNewWindow -PassThru
        Write-Host "Server process ID: $($startedProcess.Id)"
        $deadline = (Get-Date).AddSeconds(60)
        do {
            if ($startedProcess.HasExited) { throw 'The server exited before it became ready. Check its console window.' }
            if (Test-Application) { break }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        if (-not (Test-Application)) { throw 'The application did not become ready within 60 seconds.' }
    } else {
        Write-Host 'Reusing the running application server.'
    }

    Write-Host "ResumeMatch is ready: $url"
    Write-Host 'Keep the server console window open while using the application.'
    if (-not $NoBrowser) { Start-Process $url }
    if ($startedProcess) {
        Wait-Process -Id $startedProcess.Id
        if ($startedProcess.ExitCode -ne 0) { throw 'The application server stopped with an error. Check the console output above.' }
    }
} catch {
    if ($startedProcess) {
        Get-CimInstance Win32_Process -Filter "ParentProcessId = $($startedProcess.Id)" -ErrorAction Continue | ForEach-Object {
            Stop-Process -Id $_.ProcessId -ErrorAction Continue
        }
        if (-not $startedProcess.HasExited) { Stop-Process -Id $startedProcess.Id -ErrorAction Continue }
    }
    Write-Error $_
    exit 1
}
