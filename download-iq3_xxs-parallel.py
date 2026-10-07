"""Resume the pinned IQ3_XXS files using bounded parallel HTTP ranges and verify SHA-256."""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request
import setup

ROOT = Path(__file__).resolve().parent
DEST = Path('E:/Strata-data/models/IQ3_XXS')
STATUS = ROOT / 'installation-iq3_xxs-status.json'
REPO = 'ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF'
REVISION = setup.HF_REVISIONS[REPO]
WORKERS = 12
CHUNK = 16 * 1024 * 1024

def status(stage, **details):
    payload = dict(stage=stage, model='IQ3_XXS', data_dir='E:/Strata-data',
                   updated_at=datetime.now(timezone.utc).isoformat(), connections=WORKERS, **details)
    temp = STATUS.with_suffix('.download.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATUS)
    print(json.dumps(payload), flush=True)

def download_chunk(url, folder, start, end, total):
    chunk = folder / f'{start}-{end}.chunk'
    length = end - start + 1
    if chunk.exists() and chunk.stat().st_size == length:
        return chunk
    partial = chunk.with_suffix('.chunk.part')
    for attempt in range(8):
        try:
            have = partial.stat().st_size if partial.exists() else 0
            if have > length:
                raise RuntimeError('Partial chunk exceeds requested size')
            if have < length:
                first = start + have
                req = urllib.request.Request(url, headers={
                    'Range': f'bytes={first}-{end}', 'User-Agent': 'strata-local-parallel-download',
                    'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(req, timeout=90) as response:
                    wanted = f'bytes {first}-{end}/'
                    actual = response.headers.get('Content-Range', '')
                    valid = actual == wanted + str(total) if total is not None else (
                        actual.startswith(wanted) and actual[len(wanted):].isdigit()
                        and int(actual[len(wanted):]) > end)
                    if response.status != 206 or not valid:
                        raise RuntimeError('Server did not return the exact requested byte range')
                    remaining = length - have
                    with partial.open('ab') as output:
                        while remaining:
                            data = response.read(min(1024 * 1024, remaining))
                            if not data:
                                raise RuntimeError('Incomplete range response')
                            output.write(data)
                            remaining -= len(data)
            if partial.stat().st_size != length:
                raise RuntimeError('Chunk length mismatch')
            partial.replace(chunk)
            return chunk
        except Exception:
            if attempt == 7:
                raise
            time.sleep(min(30, 2 ** attempt))

def verify(path, expected):
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != expected:
        raise RuntimeError(f'SHA-256 mismatch for {path.name}: keeping file for inspection')

def main():
    url = f'https://huggingface.co/api/models/{REPO}/tree/{REVISION}/IQ3_XXS'
    with urllib.request.urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    files = [item for item in metadata if item.get('path', '').endswith('.gguf')]
    if len(files) != 2:
        raise RuntimeError('Expected exactly two pinned model shards')
    files.sort(key=lambda item: item['path'])
    DEST.mkdir(parents=True, exist_ok=True)
    total_bytes = sum(item['size'] for item in files)
    completed_bytes = 0
    started = time.monotonic()
    initial_bytes = sum((DEST / Path(item['path']).name).stat().st_size
                        if (DEST / Path(item['path']).name).exists()
                        else (DEST / (Path(item['path']).name + '.part')).stat().st_size
                        if (DEST / (Path(item['path']).name + '.part')).exists() else 0 for item in files)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for item in files:
            filename = Path(item['path']).name
            final = DEST / filename
            expected = item['lfs']['oid']
            total = item['size']
            if len(expected) != 64 or item['lfs']['size'] != total:
                raise RuntimeError('Invalid pinned LFS metadata')
            marker = final.with_name(final.name + '.sha256-verified')
            if final.exists():
                if final.stat().st_size != total:
                    raise RuntimeError('Existing final shard has an unexpected size')
                if not marker.exists() or marker.read_text().strip() != expected:
                    status('verifying_download', file=filename)
                    verify(final, expected)
                    marker.write_text(expected)
                setup.mark(final, f'sha256 {expected}')
                completed_bytes += total
                continue
            partial = final.with_name(final.name + '.part')
            chunks = DEST / (filename + '.parallel')
            chunks.mkdir(exist_ok=True)
            file_url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/{item["path"]}'
            with partial.open('ab') as output:
                have = output.tell()
                if have > total:
                    raise RuntimeError('Existing prefix is longer than the model shard')
                while have < total:
                    jobs = []
                    for i in range(WORKERS):
                        start = have + i * CHUNK
                        if start >= total:
                            break
                        end = min(start + CHUNK, total) - 1
                        jobs.append(pool.submit(download_chunk, file_url, chunks, start, end, total))
                    for future in jobs:
                        chunk = future.result()
                        with chunk.open('rb') as source:
                            shutil.copyfileobj(source, output, length=1024 * 1024)
                        output.flush()
                        have = output.tell()
                        chunk.unlink()
                    future_existing = sum(f['size'] for f in files[files.index(item)+1:]
                                          if (DEST / Path(f['path']).name).exists())
                    current = completed_bytes + have + future_existing
                    speed = max(0, current - initial_bytes) / max(1, time.monotonic() - started)
                    status('downloading', file=filename, downloaded_gb=round(current / 1e9, 2),
                           model_download_gb=round(total_bytes / 1e9, 2),
                           model_percent=round(current * 100 / total_bytes, 2),
                           average_MBps=round(speed / 1e6, 2),
                           estimated_remaining_model_hours=round((total_bytes-current)/speed/3600, 2) if speed else None)
            status('verifying_download', file=filename, downloaded_gb=round((completed_bytes + total)/1e9, 2))
            verify(partial, expected)
            partial.replace(final)
            marker.write_text(expected)
            setup.mark(final, f'sha256 {expected}')
            completed_bytes += total
    status('model_download_verified', downloaded_gb=round(total_bytes / 1e9, 2))

if __name__ == '__main__':
    main()
