param(
    [string]$TaskName = "MileON-Parsing-Hidden",
    [string]$ProjectRoot = "",
    [string]$PythonwPath = "",
    [switch]$NoAutoStart
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$RunnerPath = Join-Path $ProjectRoot "run_hidden.py"
if (-not (Test-Path $RunnerPath)) {
    throw "Runner file was not found: $RunnerPath"
}

if ([string]::IsNullOrWhiteSpace($PythonwPath)) {
    $resolvedByPy = $null
    try {
        $resolvedByPy = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
    }
    catch {
        $resolvedByPy = $null
    }

    if ($resolvedByPy) {
        $candidate = Join-Path (Split-Path $resolvedByPy -Parent) "pythonw.exe"
        if (Test-Path $candidate) {
            $PythonwPath = $candidate
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($PythonwPath)) {
        # path resolved successfully
    }
    else {
    $pythonw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($pythonw -and $pythonw.Source -notlike "*\WindowsApps\*") {
        $PythonwPath = $pythonw.Source
    }
    else {
        $python = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($python) {
            $candidate = Join-Path (Split-Path $python.Source -Parent) "pythonw.exe"
            if (Test-Path $candidate) {
                $PythonwPath = $candidate
            }
        }
    }
    }
}

if ([string]::IsNullOrWhiteSpace($PythonwPath) -or -not (Test-Path $PythonwPath)) {
    throw "Unable to resolve pythonw.exe. Pass explicit path via -PythonwPath"
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $PythonwPath -Argument "`"$RunnerPath`"" -WorkingDirectory $ProjectRoot
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$triggerStartup = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -MultipleInstances IgnoreNew

$fullTaskRegistered = $false

try {
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType S4U `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger @($triggerStartup, $triggerLogon) `
        -Settings $settings `
        -Principal $principal `
        -Description "Background launch of MileON parsing.py without visible window" | Out-Null

    $fullTaskRegistered = $true
}
catch {
    Write-Host "Full registration mode failed, trying user-mode fallback..."
}

if (-not $fullTaskRegistered) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $triggerLogon `
        -Settings $settings `
        -Description "Background launch of MileON parsing.py without visible window (user mode)" | Out-Null
}

if (-not $NoAutoStart) {
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host "Task '$TaskName' installed successfully."
Write-Host "Runner: $RunnerPath"
Write-Host "Pythonw: $PythonwPath"
Write-Host "Log: $(Join-Path $ProjectRoot 'logs\relay_background.log')"