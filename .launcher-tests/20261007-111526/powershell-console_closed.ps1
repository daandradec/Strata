. 'E:\Strata-data\start_model_qwen.ps1' -FunctionsOnly
$command = ConvertTo-StrataCmdPath 'E:\Strata\.launcher-tests\20261007-111526\mock-strata\run-iq3_s.bat'
Invoke-StrataOwnedServer -Command $command -WorkingDirectory 'E:\Strata\.launcher-tests\20261007-111526\mock-strata' -Port 62768 -LogPath 'E:\Strata\.launcher-tests\20261007-111526\powershell-console_closed.log' -StartupTimeoutSeconds 20
