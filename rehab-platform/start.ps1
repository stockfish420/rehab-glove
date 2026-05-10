param(
    [string]$SerialPort = $env:SERIAL_PORT,
    [int]$SerialBaud = 115200,
    [int]$CameraIndex = 0,
    [double]$BendSensitivity = 2.4,
    [double]$PressureSensitivity = 1.6,
    [int]$LlmTimeoutSeconds = 45,
    [string]$OllamaModel = "gemma4:e2b",
    [int]$BackendPort = 8010,
    [int]$FrontendPort = 5174
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$VisionAssetsDir = Join-Path $BackendDir "assets"
$HandLandmarkerModel = Join-Path $VisionAssetsDir "hand_landmarker.task"
$DashboardUrl = "http://localhost:$FrontendPort"
$StartedProcesses = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Test-HttpReady {
    param([string]$Url)

    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-PortInUse {
    param([int]$Port)

    try {
        $Connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        return $null -ne $Connection
    } catch {
        return $false
    }
}

function Get-AvailablePort {
    param([int]$PreferredPort)

    $Port = $PreferredPort
    while (Test-PortInUse $Port) {
        Write-Warning "Port $Port is already in use; trying $($Port + 1)."
        $Port += 1
    }

    return $Port
}

function Stop-StartedProcesses {
    Write-Host ""
    Write-Host "Stopping rehab platform services..."

    foreach ($Process in $StartedProcesses) {
        try {
            if ($Process -and -not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {
        }
    }

    foreach ($Port in @($BackendPort, $FrontendPort)) {
        try {
            $Connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
            foreach ($Connection in $Connections) {
                Stop-Process -Id $Connection.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        } catch {
        }
    }
}

function Ensure-BackendVenv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating backend virtual environment..."
        Push-Location $BackendDir
        python -m venv .venv
        Pop-Location
    }

    Write-Host "Installing backend Python dependencies..."
    Push-Location $BackendDir
    & $VenvPython -m pip install -r requirements.txt
    Pop-Location
}

function Ensure-FrontendDeps {
    $NodeModules = Join-Path $FrontendDir "node_modules"

    if (-not (Test-Path $NodeModules)) {
        Write-Host "Installing frontend npm dependencies..."
        Push-Location $FrontendDir
        npm install
        Pop-Location
    }
}

function Ensure-HandLandmarkerModel {
    if (Test-Path $HandLandmarkerModel) {
        return
    }

    Write-Host "Downloading MediaPipe hand landmarker model..."
    New-Item -ItemType Directory -Force -Path $VisionAssetsDir | Out-Null
    $ModelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    Invoke-WebRequest -Uri $ModelUrl -OutFile $HandLandmarkerModel
}

function Resolve-SerialPort {
    if ($SerialPort) {
        return $SerialPort
    }

    if (-not (Test-Path $VenvPython)) {
        return ""
    }

    $DetectedPort = & $VenvPython -c "import serial.tools.list_ports as p; ports=list(p.comports()); print(ports[0].device if ports else '')"
    return $DetectedPort.Trim()
}

function Start-OllamaIfNeeded {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Warning "Ollama CLI was not found on PATH. Start Ollama manually before using AI summaries."
        return
    }

    if (-not (Test-HttpReady "http://localhost:11434/api/tags")) {
        Write-Host "Starting Ollama..."
        $Process = Start-Process -FilePath "ollama" -ArgumentList "serve" -PassThru -WindowStyle Hidden
        $StartedProcesses.Add($Process)
        Start-Sleep -Seconds 3
    } else {
        Write-Host "Ollama is already running."
    }

    $Models = ollama list 2>$null
    if ($Models -notmatch [regex]::Escape($OllamaModel)) {
        Write-Warning "Ollama is running, but model '$OllamaModel' was not listed. Run: ollama pull $OllamaModel"
    }
}

try {
    Ensure-BackendVenv
    Ensure-FrontendDeps
    Ensure-HandLandmarkerModel

    $BackendPort = Get-AvailablePort $BackendPort
    $FrontendPort = Get-AvailablePort $FrontendPort
    $DashboardUrl = "http://localhost:$FrontendPort"

    $ResolvedSerialPort = Resolve-SerialPort
    if (-not $ResolvedSerialPort) {
        Write-Warning "No serial port was detected. Pass one explicitly, for example: .\start.ps1 -SerialPort COM3"
        $ResolvedSerialPort = "COM3"
    }

    Start-OllamaIfNeeded

    Write-Host "Starting backend on http://localhost:$BackendPort"
    Write-Host "Serial: $ResolvedSerialPort @ $SerialBaud baud"
    Write-Host "Bend sensitivity: $BendSensitivity x"
    Write-Host "Pressure sensitivity: $PressureSensitivity x"

    $BackendCommand = @"
`$env:PYTHONPATH = '$BackendDir'
`$env:SERIAL_PORT = '$ResolvedSerialPort'
`$env:SERIAL_BAUD = '$SerialBaud'
`$env:CAMERA_INDEX = '$CameraIndex'
`$env:BEND_SENSITIVITY = '$BendSensitivity'
`$env:PRESSURE_SENSITIVITY = '$PressureSensitivity'
`$env:LLM_TIMEOUT_SECONDS = '$LlmTimeoutSeconds'
`$env:HAND_LANDMARKER_MODEL = '$HandLandmarkerModel'
Set-Location '$BackendDir'
& '$VenvPython' -m uvicorn main:app --host 0.0.0.0 --port $BackendPort --reload
"@

    $BackendProcess = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $BackendCommand -PassThru
    $StartedProcesses.Add($BackendProcess)

    Write-Host "Starting frontend on http://localhost:$FrontendPort"
    $FrontendCommand = "`$env:VITE_API_URL = 'http://localhost:$BackendPort'; `$env:VITE_WS_URL = 'ws://localhost:$BackendPort/ws'; Set-Location '$FrontendDir'; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
    $FrontendProcess = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $FrontendCommand -PassThru
    $StartedProcesses.Add($FrontendProcess)

    Start-Sleep -Seconds 2
    Start-Process $DashboardUrl

    Write-Host ""
    Write-Host "REHAB PLATFORM BOOTED"
    Write-Host "Backend:   http://localhost:$BackendPort"
    Write-Host "Frontend:  $DashboardUrl"
    Write-Host "Health:    http://localhost:$BackendPort/health"
    Write-Host "Ollama:    http://localhost:11434"
    Write-Host ""
    Write-Host "Press Ctrl+C in this window to stop all services."

    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Stop-StartedProcesses
}
