param(
  [int]$SampleSeconds = 2
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$vite = Join-Path $frontend 'node_modules\vite\bin\vite.js'

if (-not (Test-Path -LiteralPath $python)) { throw "Backend virtualenv not found: $python" }
if (-not (Test-Path -LiteralPath $vite)) { throw "Vite executable not found: $vite" }

function Get-FreeLoopbackPort {
  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $listener.Start()
  try { return $listener.LocalEndpoint.Port }
  finally { $listener.Stop() }
}

function Get-ProcessFamily {
  param([int]$RootProcessId)
  $all = @(Get-CimInstance Win32_Process)
  $ids = [System.Collections.Generic.HashSet[int]]::new()
  [void]$ids.Add($RootProcessId)
  do {
    $added = $false
    foreach ($candidate in $all) {
      if ($ids.Contains([int]$candidate.ParentProcessId) -and $ids.Add([int]$candidate.ProcessId)) {
        $added = $true
      }
    }
  } while ($added)
  return @($all | Where-Object { $ids.Contains([int]$_.ProcessId) })
}

function Get-ApplicationFamilyWorkingSet {
  param([int]$RootProcessId)
  $family = @(Get-ProcessFamily -RootProcessId $RootProcessId | Where-Object { $_.Name -ne 'conhost.exe' })
  $workingSet = ($family | Measure-Object -Property WorkingSetSize -Sum).Sum
  return [long]$workingSet
}

function Measure-LocalWebProcess {
  param(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$HealthUrl
  )

  $portProcess = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden
  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  $maxWorkingSet = 0L
  $ready = $false
  try {
    while ($timer.Elapsed.TotalSeconds -lt 30) {
      $portProcess.Refresh()
      if ($portProcess.HasExited) { throw "$Name exited before its HTTP endpoint became ready." }
      $maxWorkingSet = [Math]::Max($maxWorkingSet, (Get-ApplicationFamilyWorkingSet -RootProcessId $portProcess.Id))
      try {
        $response = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 1 -UseBasicParsing
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { $ready = $true; break }
      } catch { }
      Start-Sleep -Milliseconds 100
    }
    if (-not $ready) { throw "$Name did not become ready within 30 seconds at $HealthUrl." }
    $startupMs = $timer.ElapsedMilliseconds
    $sampleUntil = [DateTime]::UtcNow.AddSeconds($SampleSeconds)
    while ([DateTime]::UtcNow -lt $sampleUntil) {
      $portProcess.Refresh()
      if ($portProcess.HasExited) { throw "$Name exited while sampling its working set." }
      $maxWorkingSet = [Math]::Max($maxWorkingSet, (Get-ApplicationFamilyWorkingSet -RootProcessId $portProcess.Id))
      Start-Sleep -Milliseconds 100
    }
    return [ordered]@{
      name = $Name
      ready_url = $HealthUrl
      startup_to_http_2xx_ms = $startupMs
      sampled_working_set_peak_mib = [Math]::Round($maxWorkingSet / 1MB, 1)
      sampling_window_seconds = $SampleSeconds
      process_scope = 'Sampled working set summed across the launched process and its descendants, excluding Windows conhost.exe; not kernel peak.'
    }
  } finally {
    $portProcess.Refresh()
    $family = @(Get-ProcessFamily -RootProcessId $portProcess.Id)
    foreach ($child in ($family | Where-Object { $_.ProcessId -ne $portProcess.Id } | Sort-Object { $_.ParentProcessId -eq $portProcess.Id })) {
      Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $portProcess.Refresh()
    if (-not $portProcess.HasExited) { Stop-Process -Id $portProcess.Id -Force }
    $portProcess.Dispose()
  }
}

$apiPort = Get-FreeLoopbackPort
$vitePort = Get-FreeLoopbackPort
$api = Measure-LocalWebProcess `
  -Name 'FastAPI + Uvicorn' `
  -FilePath $python `
  -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$apiPort") `
  -WorkingDirectory $backend `
  -HealthUrl "http://127.0.0.1:$apiPort/api/v1/health/live"
$frontendResult = Measure-LocalWebProcess `
  -Name 'Vite development server' `
  -FilePath $node `
  -ArgumentList @("`"$vite`"", '--host', '127.0.0.1', '--port', "$vitePort", '--strictPort') `
  -WorkingDirectory $frontend `
  -HealthUrl "http://127.0.0.1:$vitePort/"

$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum
$pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
$nodeVersion = (& $node --version 2>&1 | Out-String).Trim()
$npmVersion = (& (Get-Command npm.cmd -ErrorAction Stop).Source --version 2>&1 | Out-String).Trim()
[ordered]@{
  measured_at_utc = [DateTime]::UtcNow.ToString('o')
  operating_system = $os.Caption
  os_version = $os.Version
  logical_processors = $cpu.Sum
  physical_memory_mib = [Math]::Round($os.TotalVisibleMemorySize / 1024, 0)
  python = $pythonVersion
  node = $nodeVersion
  npm = $npmVersion
  api = $api
  frontend = $frontendResult
  interpretation = 'Local developer-machine process samples only. These measurements do not estimate container totals, production traffic capacity, PostgreSQL memory, or hosted reliability.'
} | ConvertTo-Json -Depth 5
