# Arranca el sitio de LatentHealth en local: un proceso, un puerto (web + modelo).
#
#   powershell -ExecutionPolicy Bypass -File web\start.ps1              # http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File web\start.ps1 -Port 8080
#   powershell -ExecutionPolicy Bypass -File web\start.ps1 -Reload      # recarga al tocar el servidor
#
# La web son archivos sueltos (web\site: HTML, CSS y JavaScript): no hay nada que compilar.
# El asistente de la app usa Claude si hay credenciales (variable ANTHROPIC_API_KEY); sin ellas
# contesta en modo guiado y la demo funciona igual.
param(
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$web = $PSScriptRoot
$root = Split-Path $web -Parent

Set-Location $root
Write-Host ''
Write-Host "LatentHealth en http://127.0.0.1:$Port   (Ctrl+C para parar)"
Write-Host "Rutas del modelo documentadas en http://127.0.0.1:$Port/api/docs"
Write-Host ''
$extra = @()
if ($Reload) { $extra = @('--reload', '--reload-dir', "$web\server") }
uv run --with-requirements "$web\server\requirements.txt" uvicorn server.main:app --app-dir "$web" --host 127.0.0.1 --port $Port @extra
