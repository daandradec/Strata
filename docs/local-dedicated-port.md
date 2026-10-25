# Use the dedicated local Strata API on port 38181

The IQ3_XXS local installation uses `http://127.0.0.1:38181/v1`.
The model still starts manually. No service, firewall rule, or network exposure was added.

## Start and select

1. Run `E:\Strata-data\start_model_qwen.ps1` manually.
2. Wait for the green `Listo: http://127.0.0.1:38181` message. Loading weights is not API readiness.
3. In Gentle Shell, run `/reload`, open `/model`, and select `qwen3.8-flash-strata`.

Closing the launcher window stops its owned server and model.
`start_web_strata.ps1` can open an existing Strata server without loading a second model.

## Keep these settings aligned

| Location | Value |
|---|---|
| `strata-iq3_xxs.json` | `port: 38181` |
| `run-iq3_xxs.bat` | `"--port" "38181"` |
| `install-iq3_xxs-local.py` | `PORT = 38181`, for future installation only |
| Gentle Shell agent `models.json` | `providers.strata.baseUrl: http://127.0.0.1:38181/v1` |

The batch argument is required: `serve/server.py` does not take its listening port
from the JSON. Removing `--port` would select the server's own default instead.
Do not rerun the installation/migration worker to change a port: it performs other
installation and cleanup operations.

The web launcher retains the old low-port search behavior. When the configured
port exceeds its implicit maximum, the effective range becomes that single port.
An explicitly supplied `-MaxPort` is never silently increased; an invalid effective
range is rejected before starting a server. An occupied foreign service is not
reused or stopped. Explicit `-PreferredPort` / `-MaxPort` ranges remain available.

## Checks and recovery

Run from the Strata repository, without loading the model:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tools -p test_dedicated_local_port.py -v
```

These checks use disposable roots and mock loopback APIs. Real model readiness and
inference must also be checked after manual startup on the new port.

Byte-exact pre-migration copies and hashes are in
`E:\Strata-data\.launcher-tests\port-38181-backup\manifest.json`.
For rollback, stop only your own launcher and restore the five affected files
listed there, then restart manually and reload Gentle Shell. Do not overwrite
later unrelated user edits; settings and the main launcher were backed up only
for preservation checks and were not changed by this migration.
