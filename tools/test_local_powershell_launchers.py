"""Exercise launcher lifetime and port selection without loading a GPU model."""
import ctypes
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from datetime import datetime

DATA = Path('E:/Strata-data')
ROOT = Path('E:/Strata/.launcher-tests') / datetime.now().strftime('%Y%m%d-%H%M%S')
ROOT.mkdir(parents=True)
PWSH = 'C:/Users/daand/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe'
POWERSHELL = 'C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'
PYTHON = 'C:/Python312/python.exe'
fixture = ROOT / 'mock-strata'
fixture.mkdir()
subprocess.run([PYTHON, '-m', 'venv', '--without-pip', str(fixture / '.venv')], check=True)
(fixture / 'serve').mkdir()
(fixture / 'serve/__init__.py').write_text('')
(fixture / 'strata-iq3_xxs.json').write_text(json.dumps({'args':['--max-context','65536']}))
server_source = '''import argparse,json,os,subprocess,sys,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);a,_=p.parse_known_args()
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(600)'])
Path('pids.json').write_text(json.dumps([os.getpid(),child.pid]))
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
  self.wfile.write(json.dumps({'status':'ok','service':'strata','loaded':True,'max_context':131072}).encode())
 def log_message(self,*args): pass
HTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
'''
(fixture / 'serve/server.py').write_text(server_source, encoding='utf-8')

def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

def wait_health(port, process):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError('Launcher exited early: ' + str(process.communicate()))
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                return json.load(response)
        except Exception:
            time.sleep(0.2)
    raise AssertionError('Mock server did not start')

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
kernel.OpenProcess.restype = ctypes.c_void_p
kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
kernel.CloseHandle.argtypes = [ctypes.c_void_p]

def alive(pid):
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) != 0
    finally:
        kernel.CloseHandle(handle)

def stopped(pids):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not any(alive(pid) for pid in pids):
            return
        time.sleep(0.2)
    raise AssertionError(f'Children survived: {pids}')

def launch(shell, script):
    return subprocess.Popen([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                            cwd=fixture, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)

results = []
for shell in (POWERSHELL, PWSH):
    for case in ('console_closed', 'pipeline_cancelled', 'web_port_fallback'):
        port = free_port()
        batch = fixture / 'run-iq3_xxs.bat'
        batch.write_text('@echo off\ncd /d "%~dp0"\n".venv\\Scripts\\python.exe" -m serve.server --port ' + str(port) + '\n')
        log = ROOT / (Path(shell).stem + '-' + case + '.log')
        command_script = (
            '. ' + ps_quote(DATA / 'start_model_qwen.ps1') + ' -FunctionsOnly\n' +
            '$command = ConvertTo-StrataCmdPath ' + ps_quote(batch) + '\n' +
            'Invoke-StrataOwnedServer -Command $command -WorkingDirectory ' + ps_quote(fixture) +
            ' -Port ' + str(port) + ' -LogPath ' + ps_quote(log) + ' -StartupTimeoutSeconds 20\n')
        listener = None
        if case == 'web_port_fallback':
            listener = socket.socket()
            listener.bind(('127.0.0.1', port))
            listener.listen()
            command_script = '& ' + ps_quote(DATA / 'start_web_strata.ps1') + ' -StrataRoot ' + ps_quote(fixture) + \
                f' -PreferredPort {port} -MaxPort {port+5} -NoBrowser\n'
            port += 1
        elif case == 'pipeline_cancelled':
            inner = ps_quote(command_script)
            command_script = (
                '$pipeline = [PowerShell]::Create()\n' +
                '[void]$pipeline.AddScript(' + inner + ')\n' +
                '$task = $pipeline.BeginInvoke()\n' +
                '$deadline = [DateTime]::UtcNow.AddSeconds(30)\n' +
                'while ([DateTime]::UtcNow -lt $deadline) {\n' +
                '  if (Test-Path ' + ps_quote(ROOT / 'cancel.flag') + ') { break }\n' +
                '  Start-Sleep -Milliseconds 100\n}\n' +
                '$pipeline.Stop()\n$pipeline.Dispose()\n')
        script = ROOT / (Path(shell).stem + '-' + case + '.ps1')
        script.write_text(command_script, encoding='utf-8')
        process = launch(shell, script)
        pids = []
        try:
            wait_health(port, process)
            if case == 'web_port_fallback':
                cfg = json.loads((fixture / 'strata-iq3_xxs.json').read_text())
                assert cfg['args'][cfg['args'].index('--max-context')+1] == '131072'
            pids = json.loads((fixture / 'pids.json').read_text())
            assert len(pids) == 2
            if case == 'pipeline_cancelled':
                (ROOT / 'cancel.flag').write_text('cancel')
                process.wait(timeout=15)
                (ROOT / 'cancel.flag').unlink()
            else:
                process.kill()  # Abrupt host/window closure: no PowerShell finally can run.
                process.wait(timeout=10)
            stopped(pids)
            results.append({'shell': Path(shell).stem, 'case': case, 'passed': True})
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if listener:
                listener.close()
            for pid in pids:
                if alive(pid):
                    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
print(json.dumps(results, indent=2))
(DATA / 'launcher-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
