# Used only after the new IQ3_XXS server and a >100K-token request have been verified.
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath 'E:\Strata\iq3_xxs-migration-plan.json' -Raw | ConvertFrom-Json
if ($plan.state -ne 'approved') { throw 'La eliminacion no esta aprobada.' }
$report = Get-Content -LiteralPath 'E:\Strata\iq3_xxs-verification.json' -Raw | ConvertFrom-Json
if ($report.health.model -ne 'qwen3.8-flash-next-iq3_xxs' -or $report.health.max_context -ne 131072 -or
    $report.long_test.usage.prompt_tokens -lt 100000) { throw 'El nuevo modelo no esta verificado.' }
$port = [int]$report.port
if ($port -lt 8080 -or $port -gt 8099) { throw 'Puerto de verificacion fuera del rango local aprobado.' }
$live = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 5
if (-not $live.loaded -or $live.model -ne 'qwen3.8-flash-next-iq3_xxs') { throw 'El nuevo modelo no esta activo.' }
$shared = 'E:\Strata-data\models\IQ3_XXS\Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00002-of-00002.gguf'
if (-not (Test-Path -LiteralPath $shared) -or (Get-Item -LiteralPath $shared).Length -ne 28800138432) {
    throw 'Falta el archivo compartido en el modelo nuevo.'
}
$directories = @('E:\Strata-data\models\IQ3_S', 'E:\Strata-data\packs\iq3_s')
$approvedFiles = @('CONTINUAR-MANANA.bat','download-iq3_s-parallel.py','increase-qwen-context.py',
    'install-iq3_s-local.py','installation-iq3_s-status.json','installation-iq3_s-worker.err',
    'installation-iq3_s-worker.out','installation-iq3_s-worker.pid','installation-iq3_s.log',
    'run-iq3_s.bat','strata-iq3_s.json','strata-iq3_s.json.before-128k-20261007-110545.bak',
    'strata-iq3_s.log','strata-iq3_s.shared-settings.json','strata-server-iq3_s.out','strata-server-iq3_s.pid')
# Validate every resolved target before performing any recursive removal.
foreach ($path in $directories) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if ($item.FullName -ne $path -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Ruta de eliminacion inesperada: $path"
        }
        if (-not $item.FullName.StartsWith('E:\Strata-data\',[StringComparison]::OrdinalIgnoreCase)) {
            throw 'Directorio fuera de Strata-data.'
        }
    }
}
foreach ($name in $approvedFiles) {
    $path = Join-Path 'E:\Strata' $name
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if ($item.PSIsContainer -or $item.DirectoryName -ne 'E:\Strata') { throw 'Archivo fuera de Strata.' }
    }
}
$unloaded = Invoke-RestMethod "http://127.0.0.1:$port/unload" -Method Post -ContentType 'application/json' -Body '{}' -TimeoutSec 120
if ($unloaded.status -eq 'busy') { throw 'El modelo esta ocupado; la limpieza se pospone.' }
try {
    # On Windows the shared lookup's open handle can prevent removing its old hard-link name.
    foreach ($path in $directories) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }
    foreach ($name in $approvedFiles) {
        $path = Join-Path 'E:\Strata' $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    }
} finally {
    Invoke-RestMethod "http://127.0.0.1:$port/load" -Method Post -ContentType 'application/json' -Body '{}' -TimeoutSec 300 | Out-Null
}
Write-Host 'Pesos, paquete, configuracion y registros exclusivos de IQ3_S eliminados.'
