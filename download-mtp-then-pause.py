"""Finish and verify the auxiliary download, then exit without packing or starting Strata."""
import concurrent.futures
import importlib.util
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time
import traceback
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import mtp_fetch

spec = importlib.util.spec_from_file_location('parallel_download', ROOT / 'download-iq3_xxs-parallel.py')
parallel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parallel)
OUT = Path('E:/Strata-data/mtp')
STATUS = ROOT / 'installation-iq3_s-status.json'
WORKERS = 12
CHUNK = 16 * 1024 * 1024

def status(stage, **details):
    payload = dict(stage=stage, model='IQ3_S', paused_after_auxiliary_download=True,
                   updated_at=datetime.now(timezone.utc).isoformat(), **details)
    temp = STATUS.with_suffix('.mtp.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATUS)
    print(json.dumps(payload), flush=True)

def main():
    inv = json.loads((OUT / 'mtp-inventory.json').read_text(encoding='utf-8'))
    if inv['repo'] != mtp_fetch.PINNED or not mtp_fetch.pinned():
        raise RuntimeError('Auxiliary inventory must use the pinned original checkpoint')
    rows = inv['tensors']
    total = inv['total_bytes']
    tensors = OUT / 'tensors'
    initial = sum((tensors / (r['name'] + '.bin')).stat().st_size
                  for r in rows if (tensors / (r['name'] + '.bin')).exists())
    started = time.monotonic()
    completed = 0
    manifest = []
    status('downloading_auxiliary', downloaded_gb=round(initial/1e9, 2), total_gb=round(total/1e9, 2), connections=WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row in rows:
            path = tensors / (row['name'] + '.bin')
            expected = mtp_fetch.SHA256[row['name']]
            chunks = OUT / 'parallel' / row['name']
            chunks.mkdir(parents=True, exist_ok=True)
            with path.open('ab') as output:
                have = output.tell()
                if have > row['bytes']:
                    raise RuntimeError('Existing auxiliary file exceeds its expected size')
                while have < row['bytes']:
                    jobs = []
                    for i in range(WORKERS):
                        offset = have + i * CHUNK
                        if offset >= row['bytes']:
                            break
                        start = row['start'] + offset
                        end = min(start + CHUNK - 1, row['end'])
                        jobs.append(pool.submit(parallel.download_chunk, inv['repo'] + row['shard'],
                                                chunks, start, end, None))
                    for future in jobs:
                        chunk = future.result()
                        with chunk.open('rb') as source:
                            shutil.copyfileobj(source, output, length=1024*1024)
                        output.flush()
                        have = output.tell()
                        chunk.unlink()
                    # Initial includes files after this row that have not been visited yet.
                    current = sum(open(p, 'rb').seek(0, 2) for p in tensors.glob('*.bin'))
                    speed = max(0, current-initial) / max(1, time.monotonic()-started)
                    status('downloading_auxiliary', downloaded_gb=round(current/1e9, 2), total_gb=round(total/1e9, 2),
                           auxiliary_percent=round(100*current/total, 1), average_MBps=round(speed/1e6, 2),
                           remaining_minutes=round((total-current)/speed/60, 1) if speed else None,
                           connections=WORKERS)
            parallel.verify(path, expected)
            completed += row['bytes']
            manifest.append(dict(row, file=str(path.relative_to(OUT)), sha256=expected))
    (OUT / 'mtp-manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    bad = mtp_fetch.verify(str(OUT))
    if bad:
        raise RuntimeError('Auxiliary verification failed: ' + str(bad))
    status('paused', auxiliary_download_verified=True, downloaded_gb=round(total/1e9, 2),
           total_gb=round(total/1e9, 2), auxiliary_percent=100,
           safe_to_shutdown=True, resume_script=str(ROOT / 'CONTINUAR-MANANA.bat'),
           message='Descarga verificada; preparación y servidor detenidos hasta que decidas continuar.')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        status('failed', error=str(error), traceback=traceback.format_exc(), safe_to_shutdown=True)
        raise
