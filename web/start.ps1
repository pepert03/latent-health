# Arranca el sitio de LatentHealth en local: un proceso, un puerto (web + modelo).
#
#   powershell -ExecutionPolicy Bypass -File web\start.ps1            # http://127.0.0.1:8000
#   powershell -ExecutionPolicy Bypass -File web\start.ps1 -Rebuild   # fuerza recompilar la web
#
# Compila la web si falta o si el código es más reciente que la última compilación.
param(
    [int]$Port = 8000,
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
$web = $PSScriptRoot
$root = Split-Path $web -Parent
$built = Join-Path $web 'dist\index.html'

function Test-Stale {
    if (-not (Test-Path $built)) { return $true }
    $builtAt = (Get-Item $built).LastWriteTimeUtc
    $sources = @(Get-ChildItem -Recurse -File (Join-Path $web 'src'), (Join-Path $web 'public')) +
        @(Get-Item (Join-Path $web 'index.html'), (Join-Path $web 'package.json'), (Join-Path $web 'vite.config.ts'))
    return [bool]($sources | Where-Object { $_.LastWriteTimeUtc -gt $builtAt } | Select-Object -First 1)
}

if ($Rebuild -or (Test-Stale)) {
    if (-not (Test-Path (Join-Path $web 'node_modules'))) {
        Write-Host 'Instalando dependencias de la web...'
        npm --prefix "$web" install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Write-Error 'npm install ha fallado.'; exit 1 }
    }
    Write-Host 'Compilando la web...'
    npm --prefix "$web" run build
    if ($LASTEXITCODE -ne 0) { Write-Error 'La compilación de la web ha fallado.'; exit 1 }
}

Set-Location $root
Write-Host ''
Write-Host "LatentHealth en http://127.0.0.1:$Port   (Ctrl+C para parar)"
Write-Host ''
uv run --with-requirements "$web\server\requirements.txt" uvicorn server.main:app --app-dir "$web" --host 127.0.0.1 --port $Port
