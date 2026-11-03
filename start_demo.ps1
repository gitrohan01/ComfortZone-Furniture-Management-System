$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$backendDirectory = Join-Path $projectRoot 'backend'
$frontendDirectory = Join-Path $projectRoot 'frontend'
$managePy = Join-Path $backendDirectory 'manage.py'
$viteEntry = Join-Path $frontendDirectory 'node_modules\vite\bin\vite.js'
$demoDirectory = Join-Path $backendDirectory '.demo-data'
$logsDirectory = Join-Path $demoDirectory 'logs'
$backendDatabase = Join-Path $demoDirectory 'showroom.sqlite3'
$testDatabase = Join-Path $backendDirectory 'test.sqlite3'
$runLogsDirectory = Join-Path $logsDirectory (Get-Date -Format 'yyyyMMdd-HHmmss-fff')

$backendProcess = $null
$frontendProcess = $null
$ownsBackend = $false
$ownsFrontend = $false
$signalHandlerRegistered = $false

function Get-PortListeners {
    param(
        [int]$Port,
        [string]$ExpectedCommandPattern
    )

    $connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -notin @('Closed', 'TimeWait') })
    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $processIds = @($connections | ForEach-Object { [int]$_.OwningProcess })
    if ($ExpectedCommandPattern) {
        $processIds += @($processes |
            Where-Object { $_.CommandLine -match $ExpectedCommandPattern } |
            ForEach-Object { [int]$_.ProcessId })
    }

    foreach ($processId in @($processIds | Select-Object -Unique)) {
        $processInfo = $processes | Where-Object { [int]$_.ProcessId -eq $processId } | Select-Object -First 1
        if (-not $processInfo) {
            $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        }
        [pscustomobject]@{
            Port = $Port
            ProcessId = $processId
            ExecutablePath = $processInfo.ExecutablePath
            CommandLine = $processInfo.CommandLine
        }
    }
}

function Test-HealthyEndpoint {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 2,
        [string[]]$ExpectedContent
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        if ($response.StatusCode -ne 200) {
            return $false
        }
        foreach ($expected in $ExpectedContent) {
            if (-not $response.Content.Contains($expected)) {
                return $false
            }
        }
        return $true
    }
    catch {
        return $false
    }
}

function Resolve-ExistingService {
    param(
        [int]$Port,
        [string]$ExpectedCommandPattern,
        [string]$HealthUri,
        [string]$ServiceName,
        [string[]]$ExpectedContent
    )

    $listeners = @(Get-PortListeners -Port $Port -ExpectedCommandPattern $ExpectedCommandPattern)
    if ($listeners.Count -eq 0) {
        return $null
    }

    foreach ($listener in $listeners) {
        Write-Host "$ServiceName port $Port is owned by PID $($listener.ProcessId)"
        Write-Host "  Executable: $($listener.ExecutablePath)"
        Write-Host "  Command:    $($listener.CommandLine)"
    }

    if ($listeners.Count -ne 1) {
        throw "Port $Port has multiple reported owners. Resolve them manually before starting the demo."
    }

    $listener = $listeners[0]
    if ($listener.CommandLine -notmatch $ExpectedCommandPattern) {
        throw "Port $Port is occupied by a process that cannot be verified as this project's $ServiceName. It was not stopped. Stop that process yourself, then rerun the launcher."
    }
    if (-not (Test-HealthyEndpoint -Uri $HealthUri -ExpectedContent $ExpectedContent)) {
        throw "Port $Port appears to belong to a $ServiceName process, but its health check failed. It was not stopped. Inspect its log/process and rerun."
    }

    Write-Host "Reusing verified $ServiceName process PID $($listener.ProcessId)."
    Write-Host '  This pre-existing service remains running when this launcher is stopped.'
    return Get-Process -Id $listener.ProcessId
}

function Wait-ForService {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$ServiceName,
        [int]$Port,
        [string]$ExpectedCommandPattern,
        [string]$HealthUri,
        [string]$LogPath,
        [string[]]$ExpectedContent
    )

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ([ComfortZoneDemoConsoleSignal]::ShutdownRequested) {
            throw "$ServiceName startup interrupted by Ctrl+C."
        }
        $Process.Refresh()
        if ($Process.HasExited) {
            $recentLog = ''
            if (Test-Path -LiteralPath $LogPath) {
                $recentLog = (Get-Content -LiteralPath $LogPath -Tail 20 | Out-String).Trim()
            }
            throw "$ServiceName exited during startup. Log: $LogPath`n$recentLog"
        }
        $listenerIds = @(Get-PortListeners -Port $Port -ExpectedCommandPattern $ExpectedCommandPattern |
            ForEach-Object { $_.ProcessId })
        if ($listenerIds -contains $Process.Id -and
            (Test-HealthyEndpoint -Uri $HealthUri -ExpectedContent $ExpectedContent)) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "$ServiceName did not become ready at $HealthUri within 30 seconds. Log: $LogPath"
}

function Stop-OwnedProcessTree {
    param([System.Diagnostics.Process]$RootProcess)

    if (-not $RootProcess) {
        return
    }

    $RootProcess.Refresh()
    if ($RootProcess.HasExited) {
        return
    }

    $processSnapshot = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $ownedIds = [System.Collections.Generic.HashSet[int]]::new()
    $null = $ownedIds.Add([int]$RootProcess.Id)
    $descendants = @()
    $foundMore = $true

    while ($foundMore) {
        $foundMore = $false
        foreach ($candidate in $processSnapshot) {
            $candidateId = [int]$candidate.ProcessId
            if (-not $ownedIds.Contains($candidateId) -and $ownedIds.Contains([int]$candidate.ParentProcessId)) {
                $null = $ownedIds.Add($candidateId)
                $descendants += $candidate
                $foundMore = $true
            }
        }
    }

    foreach ($descendant in @($descendants | Sort-Object CreationDate -Descending)) {
        $childId = [int]$descendant.ProcessId
        $stillRunning = Get-Process -Id $childId -ErrorAction SilentlyContinue
        if ($stillRunning) {
            Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
        }
    }

    $RootProcess.Refresh()
    if (-not $RootProcess.HasExited) {
        $RootProcess.Kill()
        $null = $RootProcess.WaitForExit(10000)
    }
}

try {
    Write-Host 'Resolving Node.js from this PowerShell terminal...'
    $nodeCommands = @(Get-Command node -All -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -eq 'Application' })
    $whereNode = @(& where.exe node 2>$null)
    $nodeCandidates = [System.Collections.Generic.List[string]]::new()
    foreach ($command in $nodeCommands) {
        if ($command.Source -and -not $nodeCandidates.Contains($command.Source)) {
            $nodeCandidates.Add($command.Source)
        }
    }
    foreach ($path in $whereNode) {
        $candidate = $path.Trim()
        if ($candidate -and -not $nodeCandidates.Contains($candidate)) {
            $nodeCandidates.Add($candidate)
        }
    }

    if ($nodeCommands.Count -gt 0) {
        Write-Host 'Get-Command node results:'
        foreach ($command in $nodeCommands) {
            Write-Host "  $($command.Source)"
        }
    }

    if ($whereNode.Count -eq 0) {
        Write-Host 'where.exe node: no Node executable found on PATH.'
    }
    else {
        Write-Host 'where.exe node results (PATH order):'
        foreach ($path in $whereNode) {
            Write-Host "  $path"
        }
    }

    if ($nodeCommands.Count -eq 0 -and -not $env:COMFORTZONE_DEMO_NODE) {
        throw 'Node.js was not found by Get-Command or where.exe. Install Node 22+ or set COMFORTZONE_DEMO_NODE to its full node.exe path.'
    }

    if ($env:COMFORTZONE_DEMO_NODE) {
        $nodeExecutable = [System.IO.Path]::GetFullPath($env:COMFORTZONE_DEMO_NODE)
        if (-not $nodeCandidates.Contains($nodeExecutable)) {
            $nodeCandidates.Add($nodeExecutable)
        }
        Write-Host "Selected Node executable from COMFORTZONE_DEMO_NODE: $nodeExecutable"
    }
    else {
        $nodeExecutable = $nodeCommands[0].Source
        Write-Host "Selected first Get-Command node result: $nodeExecutable"
    }

    if ($nodeCandidates.Count -gt 1) {
        Write-Host 'Multiple Node installations were detected:'
        foreach ($candidate in $nodeCandidates) {
            Write-Host "  $candidate"
        }
        Write-Host "Using: $nodeExecutable"
    }

    if (-not (Test-Path -LiteralPath $nodeExecutable -PathType Leaf)) {
        throw "Selected Node executable does not exist: $nodeExecutable"
    }

    $nodeVersionOutput = (& $nodeExecutable --version 2>&1 | Out-String).Trim()
    Write-Host "node --version: $nodeVersionOutput"
    if ($LASTEXITCODE -ne 0 -or $nodeVersionOutput -notmatch '^v?(\d+)\.') {
        throw "Could not read a valid Node.js version from '$nodeExecutable'."
    }
    $nodeMajor = [int]$Matches[1]
    if ($nodeMajor -lt 22) {
        $nodeRequirementError = "Node.js 22 or newer is required by Vite. This terminal selected $nodeExecutable ($nodeVersionOutput). Install/put Node 22+ first on this terminal's PATH, or set `$env:COMFORTZONE_DEMO_NODE to the full Node 22+ executable path. PATH will not be changed by this launcher."
        Write-Host $nodeRequirementError
    }
    else {
        Write-Host "Node.js requirement satisfied: $nodeExecutable ($nodeVersionOutput)."
    }

    $pythonCommand = Get-Command python -ErrorAction Stop
    $pythonExecutable = $pythonCommand.Source
    if (-not (Test-Path -LiteralPath $viteEntry -PathType Leaf)) {
        throw "Vite is not installed at $viteEntry. Install frontend dependencies before starting the demo."
    }
    if (-not (Test-Path -LiteralPath $backendDatabase -PathType Leaf)) {
        throw "Demo database is missing at $backendDatabase. Use the documented demo initialization commands; this launcher will not recreate it."
    }
    if (-not (Test-Path -LiteralPath $testDatabase -PathType Leaf)) {
        Write-Host 'The separate test.sqlite3 file is absent; the demo never uses it.'
    }

    $backendPattern = '(?i)(?:' + [regex]::Escape($backendDirectory) +
        '[\\/]manage\.py|manage\.py).*runserver.*127\.0\.0\.1:8002.*--settings=config\.demo_settings'
    $vitePattern = '(?i)(?:' + [regex]::Escape($viteEntry) +
            '|node_modules[\\/]vite[\\/]bin[\\/]vite\.js)' +
            '.*--host\s+127\.0\.0\.1.*--port\s+5173.*--strictPort'
    $existingBackend = Resolve-ExistingService `
        -Port 8002 `
        -ExpectedCommandPattern $backendPattern `
        -HealthUri 'http://127.0.0.1:8002/api/products/' `
        -ServiceName 'Django demo backend' `
        -ExpectedContent 'Demo Oak Lounge Chair'
    $existingFrontend = Resolve-ExistingService `
        -Port 5173 `
        -ExpectedCommandPattern $vitePattern `
        -HealthUri 'http://127.0.0.1:5173/' `
        -ServiceName 'Vite demo frontend' `
        -ExpectedContent @('<title>Comfort Zone | Admin</title>', 'src="/src/main.jsx"')

    if ($nodeMajor -lt 22) {
        throw $nodeRequirementError
    }

    if (-not ('ComfortZoneDemoConsoleSignal' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class ComfortZoneDemoConsoleSignal
{
    private delegate bool HandlerRoutine(uint controlType);
    private static readonly HandlerRoutine Handler = HandleControlEvent;
    private static int shutdownRequested;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetConsoleCtrlHandler(HandlerRoutine handler, bool add);

    public static bool ShutdownRequested
    {
        get { return Volatile.Read(ref shutdownRequested) != 0; }
    }

    public static bool Register()
    {
        Interlocked.Exchange(ref shutdownRequested, 0);
        return SetConsoleCtrlHandler(Handler, true);
    }

    public static void Unregister()
    {
        SetConsoleCtrlHandler(Handler, false);
    }

    private static bool HandleControlEvent(uint controlType)
    {
        if (controlType == 0 || controlType == 1)
        {
            Interlocked.Exchange(ref shutdownRequested, 1);
            return true;
        }
        return false;
    }
}
'@
    }
    if (-not [ComfortZoneDemoConsoleSignal]::Register()) {
        throw 'Could not register a Windows console-control handler. Run this launcher from an interactive Windows terminal.'
    }
    $signalHandlerRegistered = $true

    if (-not $existingBackend) {
        New-Item -ItemType Directory -Path $runLogsDirectory -Force | Out-Null
        Push-Location $backendDirectory
        try {
            Write-Host 'Applying any pending migrations to the dedicated demo SQLite database...'
            & $pythonExecutable $managePy migrate --noinput --settings=config.demo_settings
            if ($LASTEXITCODE -ne 0) {
                throw 'Demo database migration failed; no server was started.'
            }

            Write-Host 'Running the idempotent demo seed command...'
            & $pythonExecutable $managePy seed_demo_data --settings=config.demo_settings
            if ($LASTEXITCODE -ne 0) {
                throw 'Demo data seeding failed; no server was started.'
            }
        }
        finally {
            Pop-Location
        }

        Write-Host "Starting Django on http://127.0.0.1:8002 (logs: $runLogsDirectory)"
        $backendProcess = Start-Process `
            -FilePath $pythonExecutable `
            -ArgumentList "`"$managePy`" runserver 127.0.0.1:8002 --noreload --settings=config.demo_settings" `
            -WorkingDirectory $backendDirectory `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $runLogsDirectory 'backend.stdout.log') `
            -RedirectStandardError (Join-Path $runLogsDirectory 'backend.stderr.log') `
            -PassThru
        $ownsBackend = $true
        Wait-ForService `
            -Process $backendProcess `
            -ServiceName 'Django demo backend' `
            -Port 8002 `
            -ExpectedCommandPattern $backendPattern `
            -HealthUri 'http://127.0.0.1:8002/api/products/' `
            -LogPath (Join-Path $runLogsDirectory 'backend.stderr.log') `
            -ExpectedContent 'Demo Oak Lounge Chair'
        Write-Host 'Django demo backend is ready.'
    }
    else {
        $backendProcess = $existingBackend
    }

    if (-not $existingFrontend) {
        New-Item -ItemType Directory -Path $runLogsDirectory -Force | Out-Null
        Write-Host "Starting Vite on http://127.0.0.1:5173 (logs: $runLogsDirectory)"
        $previousApiBaseUrl = $env:VITE_API_BASE_URL
        $env:VITE_API_BASE_URL = 'http://127.0.0.1:8002/api'
        try {
            $frontendProcess = Start-Process `
                -FilePath $nodeExecutable `
                -ArgumentList "`"$viteEntry`" --host 127.0.0.1 --port 5173 --strictPort" `
                -WorkingDirectory $frontendDirectory `
                -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $runLogsDirectory 'frontend.stdout.log') `
                -RedirectStandardError (Join-Path $runLogsDirectory 'frontend.stderr.log') `
                -PassThru
            $ownsFrontend = $true
        }
        finally {
            $env:VITE_API_BASE_URL = $previousApiBaseUrl
        }
        Wait-ForService `
            -Process $frontendProcess `
            -ServiceName 'Vite frontend' `
            -Port 5173 `
            -ExpectedCommandPattern $vitePattern `
            -HealthUri 'http://127.0.0.1:5173/' `
            -LogPath (Join-Path $runLogsDirectory 'frontend.stderr.log') `
            -ExpectedContent @('<title>Comfort Zone | Admin</title>', 'src="/src/main.jsx"')
        Write-Host 'Vite frontend is ready.'
    }
    else {
        $frontendProcess = $existingFrontend
    }

    Write-Host ''
    Write-Host 'ComfortZone demo is ready:'
    Write-Host '  Backend:  http://127.0.0.1:8002'
    Write-Host '  Frontend: http://127.0.0.1:5173'
    Write-Host "  Logs:     $logsDirectory"
    Write-Host 'Press Ctrl+C in this terminal to stop services started by this launcher.'

    while (-not [ComfortZoneDemoConsoleSignal]::ShutdownRequested) {
        if ($ownsBackend) {
            $backendProcess.Refresh()
            if ($backendProcess.HasExited) {
                throw "Django exited unexpectedly. See $logsDirectory\backend.stderr.log"
            }
        }
        if ($ownsFrontend) {
            $frontendProcess.Refresh()
            if ($frontendProcess.HasExited) {
                throw "Vite exited unexpectedly. See $logsDirectory\frontend.stderr.log"
            }
        }
        Start-Sleep -Milliseconds 500
    }
}
catch {
    Write-Host "ERROR: $_"
    throw
}
finally {
    if ($signalHandlerRegistered) {
        [ComfortZoneDemoConsoleSignal]::Unregister()
    }
    if ($ownsFrontend) {
        Stop-OwnedProcessTree -RootProcess $frontendProcess
    }
    if ($ownsBackend) {
        Stop-OwnedProcessTree -RootProcess $backendProcess
    }
    if ($signalHandlerRegistered -and [ComfortZoneDemoConsoleSignal]::ShutdownRequested) {
        Write-Host 'ComfortZone demo stopped. Services started by this launcher were shut down.'
    }
    elseif ($ownsFrontend -or $ownsBackend) {
        Write-Host 'Startup ended; services started by this launcher were shut down.'
    }
}
