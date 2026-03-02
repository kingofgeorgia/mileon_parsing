param(
    [string]$Action = "",
    [string]$TaskName = "MileON-Parsing-Hidden",
    [int]$Tail = 40,
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
$PauseOnExit = [string]::IsNullOrWhiteSpace($Action)

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$LogPath = Join-Path $ProjectRoot "logs\relay_background.log"
$InstallScriptPath = Join-Path $PSScriptRoot "install_hidden_task.ps1"
$AllowedActions = @("install", "uninstall", "start", "stop", "restart", "status", "logs", "doctor")

function Resolve-Action {
    param(
        [string]$CurrentAction
    )

    if (-not [string]::IsNullOrWhiteSpace($CurrentAction)) {
        $normalized = $CurrentAction.Trim().ToLowerInvariant()
        if ($AllowedActions -contains $normalized) {
            return $normalized
        }

        throw "Unknown action '$CurrentAction'. Allowed values: $($AllowedActions -join ', ')"
    }

    Write-Host "Select action:"
    for ($index = 0; $index -lt $AllowedActions.Count; $index++) {
        $menuNumber = $index + 1
        Write-Host " [$menuNumber] $($AllowedActions[$index])"
    }

    $choiceRaw = Read-Host "Enter number"
    $parsedChoice = 0
    if (-not [int]::TryParse($choiceRaw, [ref]$parsedChoice)) {
        throw "Invalid menu choice: '$choiceRaw'"
    }

    $choice = $parsedChoice
    if ($choice -lt 1 -or $choice -gt $AllowedActions.Count) {
        throw "Menu choice out of range: $choice"
    }

    return $AllowedActions[$choice - 1]
}

function Invoke-Doctor {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "Task check: NOT FOUND ($TaskName)"
    }
    else {
        $taskInfo = $task | Get-ScheduledTaskInfo
        Write-Host "Task check: OK"
        Write-Host " - State: $($task.State)"
        Write-Host " - LastTaskResult: $($taskInfo.LastTaskResult)"
        Write-Host " - LastRunTime: $($taskInfo.LastRunTime)"
    }

    $relatedProcesses = Get-CimInstance Win32_Process |
        Where-Object {
            ($_.Name -match 'python|pythonw') -and
            ($_.CommandLine -match 'parsing.py|run_hidden.py')
        }

    $runnerCount = @($relatedProcesses | Where-Object { $_.CommandLine -match 'run_hidden.py' }).Count
    $parsingCount = @($relatedProcesses | Where-Object { $_.CommandLine -match 'parsing.py' }).Count

    Write-Host "Process check:"
    Write-Host " - run_hidden.py instances: $runnerCount"
    Write-Host " - parsing.py instances: $parsingCount"

    if ($runnerCount -gt 1 -or $parsingCount -gt 1) {
        Write-Host " - WARNING: duplicate instances detected (possible session lock)."
    }
    elseif ($runnerCount -eq 0 -and $parsingCount -eq 0) {
        Write-Host " - WARNING: no related processes found."
    }
    else {
        Write-Host " - OK: no duplicates detected."
    }

    if (Test-Path $LogPath) {
        $tailLines = Get-Content $LogPath -Tail 120
        $lockErrors = ($tailLines | Select-String -Pattern 'database is locked').Count
        $unicodeErrors = ($tailLines | Select-String -Pattern 'UnicodeEncodeError').Count

        Write-Host "Log check (last 120 lines):"
        Write-Host " - 'database is locked': $lockErrors"
        Write-Host " - 'UnicodeEncodeError': $unicodeErrors"

        if ($lockErrors -gt 0) {
            Write-Host " - WARNING: session/database lock seen recently."
        }
    }
    else {
        Write-Host "Log check: log file not found ($LogPath)"
    }
}

function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "Task '$TaskName' not found."
        return
    }

    $info = $task | Get-ScheduledTaskInfo
    [PSCustomObject]@{
        TaskName          = $TaskName
        State             = $task.State
        LastRunTime       = $info.LastRunTime
        LastTaskResult    = $info.LastTaskResult
        NumberOfMissedRuns= $info.NumberOfMissedRuns
        NextRunTime       = $info.NextRunTime
    } | Format-List
}

$Action = Resolve-Action -CurrentAction $Action

try {
    switch ($Action) {
        "install" {
            if (-not (Test-Path $InstallScriptPath)) {
                throw "Install script not found: $InstallScriptPath"
            }

            & $InstallScriptPath -TaskName $TaskName -ProjectRoot $ProjectRoot
            Show-Status
        }
        "uninstall" {
            $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if (-not $task) {
                Write-Host "Task '$TaskName' not found."
                return
            }

            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "Task '$TaskName' has been removed."
        }
        "start" {
            Start-ScheduledTask -TaskName $TaskName
            Start-Sleep -Seconds 1
            Show-Status
        }
        "stop" {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Show-Status
        }
        "restart" {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Start-ScheduledTask -TaskName $TaskName
            Start-Sleep -Seconds 1
            Show-Status
        }
        "status" {
            Show-Status
        }
        "logs" {
            if (Test-Path $LogPath) {
                Get-Content $LogPath -Tail $Tail
            }
            else {
                Write-Host "Log file not found: $LogPath"
            }
        }
        "doctor" {
            Invoke-Doctor
        }
    }
}
finally {
    if ($PauseOnExit) {
        Read-Host "Press Enter to exit"
    }
}