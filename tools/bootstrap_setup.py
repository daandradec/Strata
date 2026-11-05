"""Read-only checks and fixed, conservative Windows bootstrap profile (protocol 1).

Used only by setup.py's --bootstrap-check/--bootstrap-install. Normal setup stays
interactive and keeps its existing recommendations. No downloads or writes here.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import platform
import shutil
import uuid

PROTOCOL = 1
MODEL = "IQ3_XXS"
CONTEXT = 131072
PORT = 38181
MIN_VRAM_GIB = 19.5  # the existing >=20 GB-class recommendation for 128K


def check(s, directory):
    errors = []
    report = {"protocol": PROTOCOL, "transactional_config": True, "ok": False, "errors": errors,
              "model": MODEL, "context": CONTEXT, "port": PORT,
              "download_gb": s.MODELS[MODEL]["download_gb"]}
    if os.environ.get("STRATA_SKIP_SHA256") == "1":
        errors.append("STRATA_SKIP_SHA256 disables engine verification; clear it before safe bootstrap.")
        return report
    if not directory or not Path(directory).is_absolute():
        errors.append("An absolute --data-dir is required.")
        return report
    data = Path(directory).resolve()
    report["data_dir"] = str(data)
    if not data.is_dir() or data == s.ROOT.resolve() or data.parent != s.ROOT.resolve().parent:
        errors.append("Strata and the existing data clone must be separate sibling directories.")
    if not s.WIN or platform.machine().lower() not in ("amd64", "x86_64"):
        errors.append("The automatic profile requires Windows x64.")
    if errors:
        return report
    # These are the installer's hardware readers, not main(), --check or data_folder().
    try:
        ram = float(s.ram_gb())
        _, avx2, _ = s.cpu_info()
        page = s.page_file_gb()
        report["ram_gib"] = round(ram, 2) if math.isfinite(ram) else 0
        report["free_disk_gb"] = round(shutil.disk_usage(data).free / 1e9, 2)
        if not math.isfinite(ram) or ram < s.MODELS[MODEL]["ram_gb"]:
            errors.append(f"The automatic IQ3_XXS profile requires {s.MODELS[MODEL]['ram_gb']} GiB of physical RAM.")
        if not avx2:
            errors.append("The automatic profile requires an AVX2 CPU; experimental builds are not selected.")
        if page is not None and page < 4:
            errors.append("The Windows page file is below 4 GiB; configure it before installing.")
        nvidia = [g for g in s.gpus() if int(g.get("arch", 0)) >= 75
                  and s.gpu_problem(g) is None and s.driver_major(g) >= s.MIN_DRIVER
                  and math.isfinite(float(g.get("vram_gb", 0))) and g["vram_gb"] >= MIN_VRAM_GIB]
        if nvidia:
            gpu, backend = max(nvidia, key=lambda g: g["vram_gb"]), "cuda"
        else:
            amd = [g for g in s.amd_gpus() if s.amd_problem(g) is None and not g.get("uma")
                   and math.isfinite(float(g.get("vram_gb", 0))) and g["vram_gb"] >= MIN_VRAM_GIB]
            gpu, backend = (max(amd, key=lambda g: g["vram_gb"]), "hip") if amd else (None, None)
        if gpu is None:
            errors.append("No supported 20 GB-class discrete GPU/driver was found for the automatic 128K profile. "
                          "Use manual setup for smaller or experimental configurations.")
        else:
            report.update(backend=backend, gpu=int(gpu["index"]), gpu_name=gpu["name"])
    except Exception as error:
        errors.append(f"Hardware inspection failed ({type(error).__name__}); nothing was installed.")
    report["ok"] = not errors
    return report


def apply(s, args, report):
    """Select only this profile, never turn a hardware warning into consent."""
    if not report["ok"]:
        raise ValueError("; ".join(report["errors"]))
    args.family, args.model, args.context = "qwen", MODEL, CONTEXT
    args.port, args.host, args.browser = PORT, "127.0.0.1", False
    args.yes = args.setup = args.no_start = True
    args.vision, args.kv, args.low_ram = "no", "int8", "off"
    args.backend, args.gpu, args.gpus = report["backend"], str(report["gpu"]), None
    args.cuda = "13" if report["backend"] == "cuda" else None
    args.models_dir, args.gguf_dir = str(Path(args.data_dir) / "models"), None
    args.vram_reserve_mib, args.parallel = 1500, 1
    args.source, args.prebuilt = "huggingface", s.PREBUILT_URL
    args.experimental_speed_projection = "off"


def atomic(path, content):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_generated(root, data, path, content):
    """Journal the intended bytes BEFORE an atomic config replacement.

    The companion can safely recover after its Job Object kills the process tree:
    unknown user edits never match an intended/original hash and are left alone.
    Standalone bootstrap mode has no companion journal, but still writes atomically.
    """
    path = Path(path)
    if path.parent.resolve() != root.resolve() or path.name not in ("strata-iq3_xxs.json", "run-iq3_xxs.bat"):
        raise ValueError("Unexpected generated bootstrap file")
    state = Path(data) / ".install-state"
    journal = state / "pending.json"
    if journal.is_file():
        for item in (state, journal):
            info = item.lstat()
            if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Redirected bootstrap journal")
        record = json.loads(journal.read_text(encoding="utf-8"))
        if record.get("protocol") != 1 or record.get("fork_dir") != str(root.resolve()) or record.get("data_dir") != str(Path(data).resolve()):
            raise ValueError("Unexpected bootstrap transaction")
        record["expected"][path.name] = hashlib.sha256(content).hexdigest()
        atomic(journal, (json.dumps(record, indent=2) + "\n").encode("utf-8"))
    atomic(path, content)
