. 'E:\Strata-data\start_model_qwen.ps1' -FunctionsOnly
$command = ConvertTo-StrataCmdPath 'E:\Strata\.launcher-tests\20261007-140955\mock-strata\run-iq3_xxs.bat'
Invoke-StrataOwnedServer -Command $command -WorkingDirectory 'E:\Strata\.launcher-tests\20261007-140955\mock-strata' -Port 49284 -LogPath 'E:\Strata\.launcher-tests\20261007-140955\pwsh-console_closed.log' -StartupTimeoutSeconds 20
