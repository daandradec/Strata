$pipeline = [PowerShell]::Create()
[void]$pipeline.AddScript('. ''E:\Strata-data\start_model_qwen.ps1'' -FunctionsOnly
$command = ConvertTo-StrataCmdPath ''E:\Strata\.launcher-tests\20261007-140955\mock-strata\run-iq3_xxs.bat''
Invoke-StrataOwnedServer -Command $command -WorkingDirectory ''E:\Strata\.launcher-tests\20261007-140955\mock-strata'' -Port 63529 -LogPath ''E:\Strata\.launcher-tests\20261007-140955\powershell-pipeline_cancelled.log'' -StartupTimeoutSeconds 20
')
$task = $pipeline.BeginInvoke()
$deadline = [DateTime]::UtcNow.AddSeconds(30)
while ([DateTime]::UtcNow -lt $deadline) {
  if (Test-Path 'E:\Strata\.launcher-tests\20261007-140955\cancel.flag') { break }
  Start-Sleep -Milliseconds 100
}
$pipeline.Stop()
$pipeline.Dispose()
