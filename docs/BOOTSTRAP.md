# Conservative Windows bootstrap (local fork)

The companion `daandradec/Strata-data` repository provides
`install/Instalar-Strata.ps1` and a double-click BAT. Clone that repository first,
then run its installer. It gets this fork's `strata-local-installation` branch as
a sibling and passes the data clone's actual absolute path.

Two explicit CLI modes implement protocol 1:

- `setup.py --bootstrap-check --data-dir ABSOLUTE_PATH` prints JSON and returns
  0 only when the conservative profile passes. It does not call `data_folder`,
  create directories, save settings, download packages or start a model. Python
  must already be available; `START-HERE.bat --help` can provision Python/venv
  without entering the data selection or installation flow.
- `setup.py --bootstrap-install --data-dir ABSOLUTE_PATH` checks again, then
  uses normal setup with the fixed profile below. Other CLI overrides are
  rejected. Existing private API keys or executable hooks are not overwritten.

Profile: Qwen IQ3_XXS, context 131072, port 38181, host 127.0.0.1, KV int8, no vision,
one supported discrete GPU, VRAM reserve 1500 MiB, one request at a time and no
automatic start/browser. It uses the ordinary verified engine/model downloader
and disk-space calculation, but never scans/moves other installations or writes
the user's global Strata data-directory registry. Risk confirmations cannot be
accepted with `--yes` in this mode.

The automatic gate requires Windows x64, AVX2, physical RAM at least the existing
IQ3_XXS table's 60 GiB and a supported 20 GB-class GPU (>=19.5 GiB reported) with a
compatible driver. A page file below 4 GiB is rejected. These are conservative
automation choices, not new universal minimum requirements. Smaller/experimental
systems retain the normal manual installer unchanged. An inherited
`STRATA_SKIP_SHA256=1` bypass is rejected rather than weakening engine verification.

The check reports `transactional_config=true`. With a companion transaction in
`data/.install-state/pending.json`, the two generated config files journal their
intended SHA-256 **before** atomic replacement. The companion can distinguish its
own interrupted writes from later user edits and recover safely. The ordinary
tracked `.bak` file is left untouched in bootstrap mode; companion backups live
under the ignored data state directory. Normal setup's backup behavior is unchanged.

The legacy `--check` path is unchanged; it is **not** the read-only protocol mode.
No model is loaded by these diagnostics. Tests use mocked hardware and stop the
install path before any package/model operation:

```sh
python -m unittest tools.test_setup_bootstrap -v
```
