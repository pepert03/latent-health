# Modo desarrollo: servidor del modelo con recarga (puerto 8000, ventana aparte) y Vite con
# recarga en caliente en http://127.0.0.1:5173 (reenvía /api al 8000).
#
#   powershell -ExecutionPolicy Bypass -File web\dev.ps1
$ErrorActionPreference = 'Stop'
$web = $PSScriptRoot
$root = Split-Path $web -Parent

if (-not (Test-Path (Join-Path $web 'node_modules'))) {
    npm --prefix "$web" install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Write-Error 'npm install ha fallado.'; exit 1 }
}

$command = "Set-Location '$root'; uv run --with-requirements '$web\server\requirements.txt' " +
    "uvicorn server.main:app --app-dir '$web' --reload --reload-dir '$web\server' --host 127.0.0.1 --port 8000"
$api = Start-Process powershell -PassThru -WindowStyle Minimized -ArgumentList '-NoProfile', '-Command', $command

try {
    npm --prefix "$web" run dev
}
finally {
    taskkill /PID $api.Id /T /F | Out-Null
}
