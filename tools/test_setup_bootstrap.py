"""Safe bootstrap contract. No real hardware probes, downloads or installations."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import setup
import bootstrap_setup as bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="strata-bootstrap-contract-")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.cleanup)
        self.fork, self.data = self.base / "Strata", self.base / "Strata-data"
        self.fork.mkdir()
        self.data.mkdir()
        (self.data / ".git").mkdir()
        (self.data / ".git/config").write_text("keep git")
        (self.data / "extension.ts").write_text("keep extension")
        self.gpu = dict(index=0, name="mock RTX", vram_gb=24.0, arch="89", driver="600.0")
        patches = {
            "ROOT": self.fork, "WIN": True, "ram_gb": mock.Mock(return_value=64.0),
            "cpu_info": mock.Mock(return_value=("mock CPU", True, False)),
            "page_file_gb": mock.Mock(return_value=32), "gpus": mock.Mock(return_value=[self.gpu]),
            "amd_gpus": mock.Mock(return_value=[]),
        }
        patcher = mock.patch.multiple(setup, **patches)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, setup, "BOOTSTRAP_STRICT", False)
        self.addCleanup(setattr, setup, "BOOTSTRAP_DATA_DIR", None)
        machine = mock.patch.object(bootstrap.platform, "machine", return_value="AMD64")
        machine.start()
        self.addCleanup(machine.stop)

    def cleanup(self):
        if not self.base.name.startswith("strata-bootstrap-contract-"):
            raise RuntimeError("Unexpected temporary cleanup path")
        self.temp.cleanup()

    def check(self):
        return bootstrap.check(setup, str(self.data))

    def main(self, *args):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["setup.py", *args]), contextlib.redirect_stdout(output):
            code = setup.main()
        return code, output.getvalue()

    def test_readonly_json_mode_never_calls_data_migration_or_install(self):
        before = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with mock.patch.object(setup, "data_folder", side_effect=AssertionError("migration forbidden")), \
             mock.patch.object(setup, "save_settings", side_effect=AssertionError("settings forbidden")), \
             mock.patch.object(setup, "download", side_effect=AssertionError("download forbidden")), \
             mock.patch.object(setup, "pip_install", side_effect=AssertionError("pip forbidden")):
            code, output = self.main("--bootstrap-check", "--data-dir", str(self.data))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["ok"])
        after = {str(p.relative_to(self.base)): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_target_is_not_created(self):
        target = self.base / "missing"
        self.assertFalse(bootstrap.check(setup, str(target))["ok"])
        self.assertFalse(target.exists())

    def test_another_parent_or_same_directory_is_refused(self):
        self.assertFalse(bootstrap.check(setup, str(self.fork))["ok"])
        self.assertFalse(bootstrap.check(setup, str(self.base))["ok"])

    def test_insufficient_ram_is_not_accepted_by_yes(self):
        setup.ram_gb.return_value = 32
        code, output = self.main("--bootstrap-check", "--data-dir", str(self.data))
        self.assertEqual(code, 1)
        self.assertIn("physical RAM", json.loads(output)["errors"][0])

    def test_smaller_gpu_does_not_silently_reduce_context(self):
        self.gpu["vram_gb"] = 16
        report = self.check()
        self.assertFalse(report["ok"])
        self.assertEqual(report["context"], 131072)

    def test_old_driver_or_experimental_gpu_is_refused(self):
        for updates in (dict(driver="500.0"), dict(arch="60")):
            with self.subTest(updates=updates):
                gpu = {**self.gpu, **updates}
                setup.gpus.return_value = [gpu]
                self.assertFalse(self.check()["ok"])

    def test_avx2_and_page_file_are_checked(self):
        setup.cpu_info.return_value = ("mock", False, False)
        self.assertFalse(self.check()["ok"])
        setup.cpu_info.return_value = ("mock", True, False)
        setup.page_file_gb.return_value = 1
        self.assertFalse(self.check()["ok"])

    def test_supported_discrete_amd_is_selected_when_no_nvidia(self):
        setup.gpus.return_value = []
        setup.amd_gpus.return_value = [dict(index=1, name="mock Radeon", arch="gfx1100", vram_gb=24)]
        report = self.check()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["backend"], "hip")

    def test_non_windows_never_probes_hardware(self):
        setup.WIN = False
        self.assertFalse(self.check()["ok"])
        setup.gpus.assert_not_called()

    def test_engine_verification_bypass_is_not_inherited_silently(self):
        with mock.patch.dict(bootstrap.os.environ, {"STRATA_SKIP_SHA256": "1"}):
            self.assertFalse(self.check()["ok"])
        setup.gpus.assert_not_called()

    def test_strict_risk_refuses_explicit_yes_but_legacy_mode_is_unchanged(self):
        setup.BOOTSTRAP_STRICT = True
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            setup.confirm_risk("warning", True, True, "unsafe")
        setup.BOOTSTRAP_STRICT = False
        with contextlib.redirect_stdout(io.StringIO()):
            setup.confirm_risk("warning", True, True, "unsafe")

    def test_extra_flags_cannot_override_the_fixed_profile(self):
        for extra in (("--model", "Q2_0"), ("--yes",), ("--host", "0.0.0.0"), ("--inspect", "file.gguf")):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.main("--bootstrap-install", "--data-dir", str(self.data), *extra)
        self.assertEqual(list(self.fork.iterdir()), [])

    def test_install_mode_does_not_migrate_or_write_user_settings(self):
        # Stop at the first normal hardware probe after profile preparation, before
        # any package/engine/model operation can run.
        report = self.check()
        with mock.patch.object(bootstrap, "check", return_value=report), \
             mock.patch.object(setup, "data_folder", side_effect=AssertionError("migration forbidden")), \
             mock.patch.object(setup, "save_settings", side_effect=AssertionError("settings forbidden")), \
             mock.patch.object(setup, "gpus", side_effect=RuntimeError("stop before installation")):
            with self.assertRaisesRegex(RuntimeError, "stop before installation"):
                self.main("--bootstrap-install", "--data-dir", str(self.data))
        self.assertEqual((self.data / ".git/config").read_text(), "keep git")

    def test_private_or_executable_config_is_preserved(self):
        target = self.fork / "strata-iq3_xxs.json"
        for key in ("before_load", "api_key", "mcp_servers"):
            original = json.dumps({key: "synthetic customization"}).encode()
            target.write_bytes(original)
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                self.main("--bootstrap-install", "--data-dir", str(self.data))
            self.assertEqual(target.read_bytes(), original)

    def test_generated_bytes_are_journaled_before_atomic_replacement(self):
        import hashlib
        state = self.data / ".install-state"
        state.mkdir()
        journal = state / "pending.json"
        journal.write_text(json.dumps(dict(protocol=1,fork_dir=str(self.fork.resolve()),
                           data_dir=str(self.data.resolve()),expected={})))
        target = self.fork / "strata-iq3_xxs.json"
        original = bootstrap.atomic
        def checked(path, content):
            if path == target:
                self.assertEqual(json.loads(journal.read_text())["expected"][target.name], hashlib.sha256(content).hexdigest())
            return original(path, content)
        with mock.patch.object(bootstrap, "atomic", side_effect=checked):
            bootstrap.write_generated(self.fork,self.data,target,b'{"new":true}')
        self.assertEqual(target.read_bytes(),b'{"new":true}')

    def test_bootstrap_does_not_dirty_the_legacy_tracked_bak_file(self):
        setup.BOOTSTRAP_STRICT = True
        setup.BOOTSTRAP_DATA_DIR = self.data
        target = self.fork / "strata-iq3_xxs.json"
        target.write_text('{"port":8081}')
        backup = self.fork / "strata-iq3_xxs.json.bak"
        backup.write_bytes(b"existing tracked backup")
        with contextlib.redirect_stdout(io.StringIO()):
            setup.write_setup_config(target,{"port":38181})
        self.assertEqual(backup.read_bytes(),b"existing tracked backup")
        self.assertEqual(json.loads(target.read_text())["port"],38181)


if __name__ == "__main__":
    unittest.main()
