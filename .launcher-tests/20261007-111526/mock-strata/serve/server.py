import argparse,json,os,subprocess,sys,time
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
