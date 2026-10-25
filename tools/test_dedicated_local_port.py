"""Public launcher probes using disposable roots and mock APIs, never a GPU model.

Run: python -m unittest discover -s tools -p test_dedicated_local_port.py -v
STRATA_WEB_LAUNCHER may select a scratch copy for differential checks.
"""
import ast
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('E:/Strata-data')
WEB = Path(os.environ.get('STRATA_WEB_LAUNCHER', DATA / 'start_web_strata.ps1'))
MAIN = DATA / 'start_model_qwen.ps1'
PORT = 38181
RANGE_ERROR = 'MaxPort debe ser igual o mayor que PreferredPort.'


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@contextmanager
def api(low=False, service='strata'):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(dict(status='ok', service=service, loaded=True,
                                   max_context=131072)).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = None
    for port in range(8080, 8100) if low else [0]:
        try:
            server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError('No low-range fixture port is available')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        parent = DATA / '.launcher-tests'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='port-probe-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        python = self.root / '.venv/Scripts/python.exe'
        python.parent.mkdir(parents=True)
        # Reuse/rejection probes must never execute this placeholder.
        python.touch()
        (self.root / 'run-iq3_xxs.bat').write_text('@exit /b 97\n')
        self.config = self.root / 'strata-iq3_xxs.json'

    def configure(self, port):
        self.config.write_text(json.dumps(dict(port=port, args=['--max-context', '131072'])))
        self.before = self.config.read_bytes()

    def invoke(self, *options, launcher=WEB):
        command = '& ' + quote(launcher) + ' -StrataRoot ' + quote(self.root)
        command += ' ' + ' '.join(options)
        command = "try { " + command + " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                               '-ExecutionPolicy', 'Bypass', '-Command', command],
                              capture_output=True, text=True, timeout=12)

    def unchanged(self):
        self.assertEqual(self.config.read_bytes(), self.before)
        self.assertFalse((self.root / 'logs').exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ['.venv', 'run-iq3_xxs.bat', 'strata-iq3_xxs.json'])

    def reused(self, result, port):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout,
                         f'Strata ya esta activo: http://127.0.0.1:{port}\n'
                         'Se reutiliza ese servidor. Su cierre corresponde a la consola o proceso que lo inicio.\n')
        self.unchanged()

    def rejected(self, result, message):
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, message + '\n')
        self.unchanged()

    def test_configured_high_port_reuses_existing_server(self):
        with api() as port:
            self.configure(port)
            self.reused(self.invoke('-NoBrowser'), port)

    def test_configured_high_port_respects_explicit_max(self):
        with api() as port:
            self.configure(port)
            self.rejected(self.invoke('-NoBrowser', '-MaxPort 10000'), RANGE_ERROR)

    def test_legacy_low_port_reuse_is_preserved(self):
        with api(low=True) as port:
            self.configure(port)
            self.reused(self.invoke('-NoBrowser'), port)

    def test_explicit_high_range_reuse_is_preserved(self):
        with api() as port:
            self.configure(port)
            self.reused(self.invoke('-NoBrowser', f'-PreferredPort {port}', f'-MaxPort {port}'), port)

    def test_explicit_invalid_range_is_preserved(self):
        self.configure(PORT)
        self.rejected(self.invoke('-NoBrowser', '-PreferredPort 12000', '-MaxPort 11999'), RANGE_ERROR)

    def test_foreign_service_is_not_reused_or_replaced(self):
        with api(service='not-strata') as port:
            self.configure(port)
            self.rejected(self.invoke('-NoBrowser'), f'No hay un puerto libre entre {port} y {port}.')
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pass

    def test_main_launcher_keeps_occupied_configured_port_guard(self):
        with api() as port:
            self.configure(port)
            self.rejected(self.invoke(launcher=MAIN),
                          'El puerto configurado ya esta ocupado. Este script no detiene servidores ajenos. '
                          'Para abrir Strata existente, usa start_web_strata.ps1.')


class ConfigurationTests(unittest.TestCase):
    def test_strata_config_port(self):
        config = json.loads((ROOT / 'strata-iq3_xxs.json').read_text())
        self.assertEqual(config['port'], PORT)
        self.assertEqual(config['host'], '127.0.0.1')
        self.assertEqual(config['args'][config['args'].index('--max-context') + 1], '131072')

    def test_batch_port(self):
        self.assertIn(f'"--port" "{PORT}"', (ROOT / 'run-iq3_xxs.bat').read_text())

    def test_installer_default_without_running_installer(self):
        tree = ast.parse((ROOT / 'install-iq3_xxs-local.py').read_text(encoding='utf-8'))
        values = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'PORT' for t in node.targets)]
        self.assertEqual(values, [PORT])

    def test_gentle_shell_provider_url(self):
        config = json.loads(Path('C:/Users/daand/.gentle-shell/agent/models.json').read_text())
        self.assertEqual(config['providers']['strata']['baseUrl'], f'http://127.0.0.1:{PORT}/v1')


if __name__ == '__main__':
    unittest.main()
