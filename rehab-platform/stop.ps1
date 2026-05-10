param(
    [int[]]$Ports = @(8000, 8010, 8011, 8012, 5173, 5174, 5175, 5176),
    [switch]$StopOllama
)

$ErrorActionPreference = "SilentlyContinue"

$Root = (Split-Path -Parent $MyInvocation.MyCommand.Path).ToLowerInvariant()
$Stopped = New-Object System.Collections.Generic.HashSet[int]

function Stop-ProcessId {
    param([int]$ProcessId, [string]$Reason)

    if ($ProcessId -le 0 -or $Stopped.Contains($ProcessId)) {
        return
    }

    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $Process) {
        return
    }

    Write-Host "Stopping PID $ProcessId ($($Process.ProcessName)) - $Reason"
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    [void]$Stopped.Add($ProcessId)
}

function Stop-ProcessesOnPorts {
    foreach ($Port in $Ports) {
        $Connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        foreach ($Connection in $Connections) {
            Stop-ProcessId -ProcessId $Connection.OwningProcess -Reason "listening on port $Port"
        }
    }
}

function Stop-ProjectProcesses {
    $Processes = Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Contains($Root) -and
            (
                $_.Name -match "python|uvicorn|node|npm|powershell"
            )
        }

    foreach ($Process in $Processes) {
        if ($Process.ProcessId -ne $PID) {
            Stop-ProcessId -ProcessId $Process.ProcessId -Reason "command line references rehab-platform"
        }
    }
}

function Stop-OllamaServe {
    if (-not $StopOllama) {
        return
    }

    $Processes = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match "ollama" -and
            $_.CommandLine -and
            $_.CommandLine.ToLowerInvariant().Contains("serve")
        }

    foreach ($Process in $Processes) {
        Stop-ProcessId -ProcessId $Process.ProcessId -Reason "ollama serve requested"
    }
}

Write-Host "Stopping rehab platform processes..."
Stop-ProcessesOnPorts
Stop-ProjectProcesses
Stop-OllamaServe

if ($Stopped.Count -eq 0) {
    Write-Host "No matching rehab platform processes were found."
} else {
    Write-Host "Stopped $($Stopped.Count) process(es)."
}
