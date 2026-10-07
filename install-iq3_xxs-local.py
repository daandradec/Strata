"""Complete the approved IQ3_XXS migration, verify 128K, then remove only approved IQ3_S artifacts."""
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parent
DATA = Path('E:/Strata-data')
PYTHON = ROOT / '.venv/Scripts/python.exe'
STATUS = ROOT / 'installation-iq3_xxs-status.json'
LOG = ROOT / 'installation-iq3_xxs.log'
CONFIG = ROOT / 'strata-iq3_xxs.json'
PORT = 8081

def status(stage, **details):
    record = dict(stage=stage, model='IQ3_XXS', context=131072,
                  updated_at=datetime.now(timezone.utc).isoformat(), **details)
    temp = STATUS.with_suffix('.worker.tmp')
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATUS)
    print(json.dumps(record, ensure_ascii=False), flush=True)

def wait_for_process(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if handle:
        try:
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        finally:
            kernel.CloseHandle(handle)

def request(path, body=None, timeout=10):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}' + path,
          data=json.dumps(body).encode() if body is not None else None,
          headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def chat(prompt, timeout=600):
    return request('/v1/chat/completions', {'model':'strata', 'messages':[{'role':'user','content':prompt}],
        'max_tokens':40, 'temperature':0, 'reasoning_effort':'none'}, timeout)

def update_launchers_and_codex():
    profile = Path('C:/Users/daand/.codex/qwen.config.toml')
    catalog = Path('C:/Users/daand/.codex/model-catalogs/strata.json')
    text = profile.read_text(encoding='utf-8-sig')
    text, count = re.subn(r'(?m)^model\s*=.*$', 'model = "qwen3.8-flash-next-iq3_xxs"', text)
    if count != 1:
        raise RuntimeError('Unexpected Codex profile model entry')
    text = re.sub(r'(?m)^model_context_window\s*=.*$', 'model_context_window = 131072', text)
    text = re.sub(r'(?m)^model_auto_compact_token_limit\s*=.*$', 'model_auto_compact_token_limit = 110000', text)
    profile.write_text(text, encoding='utf-8')
    doc = json.loads(catalog.read_text(encoding='utf-8'))
    model = next(m for m in doc['models'] if m['slug'].startswith('qwen3.8-flash-next-iq3_'))
    model.update(slug='qwen3.8-flash-next-iq3_xxs', display_name='Qwen 3.8 Flash IQ3_XXS (Strata local)',
                 description='Local IQ3_XXS through Strata. Text only, 131,072-token context.',
                 context_window=131072, max_context_window=131072)
    catalog.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    base = Path('C:/Users/daand/.codex/config.toml')
    original = base.read_text(encoding='utf-8-sig')
    parsed_before = tomllib.loads(original)
    def provider_table(match):
        header, body = match.group(1), match.group(2)
        body, count = re.subn(r'(?m)^base_url\s*=.*$', f'base_url = "http://127.0.0.1:{PORT}/v1"', body)
        if count != 1:
            raise RuntimeError('Unexpected Strata provider base URL')
        return header + body
    updated, count = re.subn(r'(?ms)(^\[model_providers\.strata\]\s*\n)(.*?)(?=^\[|\Z)', provider_table, original)
    if count != 1:
        raise RuntimeError('Missing Strata provider table')
    parsed_after = tomllib.loads(updated)
    parsed_after['model_providers']['strata']['base_url'] = parsed_before['model_providers']['strata']['base_url']
    if parsed_after != parsed_before:
        raise RuntimeError('Unexpected change to GPT configuration')
    base.write_text(updated, encoding='utf-8')
    for path in (DATA / 'start_model_qwen.ps1', DATA / 'start_web_strata.ps1',
                 ROOT / 'tools/test_local_powershell_launchers.py', ROOT / 'configure-codex-strata.py'):
        source = path.read_text(encoding='utf-8')
        source = source.replace('IQ3_S', 'IQ3_XXS').replace('iq3_s', 'iq3_xxs')
        if path.name == 'start_model_qwen.ps1':
            source = source.replace("if (-not (Test-StrataPortAvailable -Port 8080)) {",
                "$modelConfig = Get-Content -LiteralPath (Join-Path $StrataRoot 'strata-iq3_xxs.json') -Raw | ConvertFrom-Json\n"
                "$modelPort = if ($modelConfig.PSObject.Properties['port']) { [int]$modelConfig.port } else { 8080 }\n"
                "if (-not (Test-StrataPortAvailable -Port $modelPort)) {")
            source = source.replace("El puerto 8080 ya esta ocupado.", "El puerto configurado ya esta ocupado.")
            source = source.replace("('model-8080-' +", "('model-' + $modelPort + '-' +")
            source = source.replace('-Port 8080 -LogPath $log', '-Port $modelPort -LogPath $log')
        elif path.name == 'start_web_strata.ps1':
            source = source.replace('# Only probe occupied ports;',
                "$modelConfig = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json\n"
                "if (-not $PSBoundParameters.ContainsKey('PreferredPort') -and $modelConfig.PSObject.Properties['port']) {\n"
                "    $PreferredPort = [int]$modelConfig.port\n}\n"
                '# Only probe occupied ports;')
        path.write_text(source, encoding='utf-8')
    # The generic auxiliary downloader uses only the range helper from this module.
    path = ROOT / 'download-mtp-then-pause.py'
    if path.exists():
        path.write_text(path.read_text(encoding='utf-8').replace('download-iq3_s-parallel.py',
                        'download-iq3_xxs-parallel.py'), encoding='utf-8')

def long_context_prompt():
    sys.path.insert(0, str(ROOT / 'tools'))
    import strata_tokenizer as ST
    directory = Path(json.loads(CONFIG.read_text())['tokenizer'])
    vocab = json.loads((directory / 'vocab.json').read_text(encoding='utf-8'))
    tokens = [None] * len(vocab)
    for token, index in vocab.items():
        tokens[index] = token
    tokenizer = ST.Tokenizer(tokens, (directory / 'merges.txt').read_text(encoding='utf-8').split('\n'),
                             json.loads((directory / 'token_type.json').read_text()))
    filler = 'Este registro describe una prueba local de contexto y no contiene la respuesta.\n' * 20000
    ids = tokenizer.encode(filler)
    if len(ids) < 120000:
        raise RuntimeError('Long-context fixture too short')
    text = tokenizer.decode(ids[:120000])
    middle = text.rfind('\n', 0, len(text)//2) + 1
    return text[:middle] + '\nEl codigo secreto de esta prueba es: contexto-verificado-128k.\n' + text[middle:] + \
        '\nIndica el codigo secreto escrito dentro del texto. Responde solamente con ese codigo.'

def main():
    if (ROOT / 'iq3_xxs-migration.paused').exists():
        status('paused', waiting_for_user_to_continue=True, old_iq3_s_retained=True)
        return
    plan = json.loads((ROOT / 'iq3_xxs-migration-plan.json').read_text())
    if plan.get('state') != 'approved':
        raise RuntimeError('Migration has not been approved')
    status('downloading', new_download_gb=47.04, reused_lookup_gb=28.8)
    for pid in map(int, sys.argv[1:]):
        wait_for_process(pid)
    env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    with LOG.open('a', encoding='utf-8') as log:
        subprocess.run([str(PYTHON), '-u', 'download-iq3_xxs-parallel.py'], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        status('installing')
        # Fresh pack/config: normal RAM mode, automatic hardware settings, 8-bit KV, GPU/display reserve.
        command = [str(PYTHON), '-u', 'setup.py', '--yes', '--family', 'qwen', '--model', 'IQ3_XXS',
            '--context', '131072', '--kv', 'int8', '--vision', 'no', '--gpu', '0',
            '--data-dir', str(DATA), '--host', '127.0.0.1', '--port', str(PORT),
            '--vram-reserve-mib', '1500', '--no-browser', '--no-start']
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(PYTHON), '-m', 'pip', 'check'], cwd=ROOT, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    cfg = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    if cfg.get('host') != '127.0.0.1' or cfg.get('mcp_servers') or cfg.get('before_load'):
        raise RuntimeError('Unexpected network or executable hooks in clean config')
    status('waiting_for_resources', port=PORT, minimum_available_ram_gib=46)
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong),
            ('total_ram',ctypes.c_ulonglong),('available_ram',ctypes.c_ulonglong),
            ('total_commit',ctypes.c_ulonglong),('available_commit',ctypes.c_ulonglong),
            ('total_virtual',ctypes.c_ulonglong),('available_virtual',ctypes.c_ulonglong),
            ('extended',ctypes.c_ulonglong)]
    while True:
        if (ROOT / 'iq3_xxs-migration.paused').exists():
            status('paused', waiting_for_user_to_continue=True, old_iq3_s_retained=True)
            return
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise RuntimeError('Cannot read Windows memory status')
        if memory.available_ram >= 46*1024**3:
            break
        status('waiting_for_resources', available_ram_gib=round(memory.available_ram/1024**3,1),
               minimum_available_ram_gib=46, port=PORT)
        time.sleep(20)
    # Never take over another process that may have started while the model downloaded.
    import socket
    with socket.socket() as port_check:
        port_check.bind(('127.0.0.1', PORT))
    status('starting')
    with (ROOT / 'strata-server-iq3_xxs.out').open('a', encoding='utf-8') as output:
        server = subprocess.Popen([str(PYTHON), '-u', '-m', 'serve.server', '--engine', 'strata',
            '--config', str(CONFIG), '--host', '127.0.0.1', '--port', str(PORT)], cwd=ROOT, env=env,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT / 'strata-server-iq3_xxs.pid').write_text(str(server.pid), encoding='utf-8')
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f'Server exited {server.returncode}; see strata-server-iq3_xxs.out. Old model retained.')
        try:
            health = request('/health')
            if health.get('loaded') and health.get('max_context') == 131072 and \
                    health.get('model') == 'qwen3.8-flash-next-iq3_xxs':
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        raise RuntimeError('Server was not ready after 30 minutes; old model retained')
    short = chat('Calcula 17 + 25. Responde solamente con el numero.')
    if short['choices'][0]['message'].get('content', '').strip() != '42':
        raise RuntimeError('Basic answer test failed; old model retained')
    status('testing_long_context')
    long = chat(long_context_prompt(), timeout=1200)
    answer = long['choices'][0]['message'].get('content', '')
    if long['usage']['prompt_tokens'] < 100000 or 'contexto-verificado-128k' not in answer:
        raise RuntimeError('Long-context verification failed; old model retained')
    update_launchers_and_codex()
    report = {'health':health, 'models':request('/v1/models'), 'short_test':short,
              'long_test':long, 'metrics':request('/metrics'), 'server_pid':server.pid,
              'auto_compact_token_limit':110000, 'port':PORT}
    (ROOT / 'iq3_xxs-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    status('cleaning_old_model', long_prompt_tokens=long['usage']['prompt_tokens'])
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(ROOT / 'remove-approved-iq3_s.ps1')], cwd=ROOT, check=True)
    plan['state'] = 'complete'
    (ROOT / 'iq3_xxs-migration-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    status('verified', health=health, server_pid=server.pid, long_prompt_tokens=long['usage']['prompt_tokens'],
           long_test_answer=answer, old_iq3_s_removed=True, auto_compact_token_limit=110000,
           url=f'http://127.0.0.1:{PORT}')

if __name__ == '__main__':
    # Tokenization needs the pinned dependencies in Strata's private environment.
    if Path(sys.executable).resolve() != PYTHON.resolve():
        raise SystemExit(subprocess.call([str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT))
    try:
        main()
    except Exception as error:
        status('failed', error=str(error), traceback=traceback.format_exc(), old_model_retained=True)
        raise
