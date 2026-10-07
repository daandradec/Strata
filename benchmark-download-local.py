import concurrent.futures
import json
import time
import urllib.request
import setup

family = setup.FAMILIES['qwen']
url = family['hf'].format(q='IQ3_S') + family['file'].format(q='IQ3_S', i=1)
size = 2 * 1024 * 1024

def fetch(i):
    start = 8_000_000_000 + i * size
    req = urllib.request.Request(url, headers={'Range': f'bytes={start}-{start+size-1}', 'User-Agent': 'strata-download-benchmark'})
    with urllib.request.urlopen(req, timeout=45) as response:
        expected = f'bytes {start}-{start+size-1}/'
        if response.status != 206 or not response.headers.get('Content-Range', '').startswith(expected):
            raise RuntimeError('Server did not honor the exact byte range')
        data = response.read(size + 1)
        if len(data) != size:
            raise RuntimeError('Unexpected response size')
    return len(data)

for count in (1, 4):
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(fetch, range(count)))
    seconds = time.monotonic() - started
    print(json.dumps({'connections': count, 'bytes': sum(results), 'seconds': round(seconds, 2),
                      'MBps': round(sum(results) / seconds / 1e6, 2)}), flush=True)
