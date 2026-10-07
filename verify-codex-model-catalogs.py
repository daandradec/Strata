import json
from pathlib import Path
import queue
import subprocess
import threading
import tomllib

EXE = Path('C:/Program Files/WindowsApps/OpenAI.Codex_26.930.7945.0_x64__2p2nqsd0c76g0/app/resources/codex.exe')

def check(profile=None):
    command = [str(EXE)]
    command += ['app-server', '--stdio']
    if profile:
        config = tomllib.loads(Path('C:/Users/daand/.codex/qwen.config.toml').read_text(encoding='utf-8'))
        for key, value in config.items():
            command += ['-c', key + '=' + json.dumps(value)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8')
    messages = queue.Queue()
    def read():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
        messages.put({'error': 'app-server closed stdout'})
    threading.Thread(target=read, daemon=True).start()
    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
    def receive(id):
        for _ in range(200):
            result = messages.get(timeout=60)
            if result.get('id') == id:
                if 'error' in result:
                    raise RuntimeError(str(result['error']))
                return result['result']
            if 'error' in result and 'id' not in result:
                raise RuntimeError(str(result['error']))
        raise RuntimeError('Too many notifications')
    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'strata-model-catalog-verification', 'version': '1.0'},
            'capabilities': {'experimentalApi': True}}})
        receive(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'model/list', 'params': {'includeHidden': False, 'limit': 100}})
        result = receive(2)
        return [{'id': m['id'], 'model': m['model'], 'displayName': m['displayName']} for m in result['data']]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

report = {'default': check(), 'qwen_profile': check('qwen')}
Path('E:/Strata/codex-strata-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
