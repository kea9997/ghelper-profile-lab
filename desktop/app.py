"""Windows companion. Loopback-only UI with per-launch capability token."""
import argparse, hmac, json, os, secrets, sys, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core import Lab
from updater import UpdateService

def create_server(lab, assets, token, port=0, closing=None, on_shutdown=None, community=None, updates=None):
    closing = closing or threading.Event()
    updating = threading.Event()
    update_lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def send(self,obj,status=200,filename=None):
            payload=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if filename: self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.end_headers(); self.wfile.write(payload)
        def authorized(self):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}': return False
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{self.server.server_port}': return False
            return hmac.compare_digest(self.headers.get('X-Session-Token',''),token)
        def do_GET(self):
            parsed=urlparse(self.path)
            if parsed.path=='/':
                qs=parse_qs(parsed.query)
                if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}' or not hmac.compare_digest(qs.get('session',[''])[0],token):
                    self.send({'error':'실행 파일에서 프로그램을 여세요.'},403); return
                html=(assets/'web'/'index.html').read_text(encoding='utf-8')
                for marker, name in {'__APP_STYLE__':'style.css','__SETTINGS_STYLE__':'settings-view.css','__SETTINGS_JS__':'settings-view.js','__SCORE_CARD_JS__':'score-card.js','__APP_JS__':'app.js','__LIBRARY_JS__':'library.js'}.items():
                    if marker in html: html=html.replace(marker,(assets/'web'/name).read_text(encoding='utf-8'))
                html=html.replace('__SESSION_TOKEN__',token).encode()
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(html)))
                self.send_header('Cache-Control','no-store'); self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                self.end_headers(); self.wfile.write(html); return
            if not self.authorized(): self.send({'error':'세션 인증 실패'},403); return
            try:
                if parsed.path=='/api/state': self.send(lab.state())
                elif parsed.path=='/api/update/check':
                    if updates is None: raise ValueError('업데이트 확인을 사용할 수 없습니다.')
                    self.send(updates.check())
                elif parsed.path=='/api/profiles/export': self.send(lab.profile(parse_qs(parsed.query).get('id',[''])[0]),filename='profile.ghprofile.json')
                elif parsed.path.startswith('/api/community/'):
                    if community is None: raise ValueError('자료실 연결을 사용할 수 없습니다.')
                    qs=parse_qs(parsed.query)
                    if parsed.path=='/api/community/browse': self.send(community.browse(qs.get('model',[''])[0],qs.get('cursor',[None])[0],qs.get('q',[''])[0]))
                    elif parsed.path=='/api/community/post': self.send(community.detail(qs.get('id',[''])[0]))
                    elif parsed.path=='/api/community/owned': self.send({'posts':community.owned()})
                    else: self.send({'error':'찾을 수 없습니다.'},404)
                else: self.send({'error':'찾을 수 없습니다.'},404)
            except (ValueError,OSError) as e: self.send({'error':str(e)},400)
        def do_POST(self):
            if not self.authorized(): self.send({'error':'세션 인증 실패'},403); return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n<0 or n>1024*1024: raise ValueError('요청 크기 제한을 초과했습니다.')
                if not self.headers.get('Content-Type','').startswith('application/json'): raise ValueError('JSON 요청이 필요합니다.')
                body=json.loads(self.rfile.read(n))
                if not isinstance(body,dict): raise ValueError('요청 형식 오류')
                path=urlparse(self.path).path
                remote_routes={
                    '/api/community/import':lambda:community.import_post(body['id']),
                    '/api/community/publish':lambda:community.publish(body['profileId'],body.get('runIds',[]),body.get('author','익명'),body['requestId']),
                    '/api/community/retry':lambda:community.retry(body['requestId']),
                    '/api/community/delete':lambda:community.delete_post(body['id']),
                }
                if path in remote_routes:
                    if community is None: raise ValueError('자료실 연결을 사용할 수 없습니다.')
                    if closing.is_set(): raise ValueError('프로그램을 종료하고 있습니다.')
                    self.send(remote_routes[path]()); return
                if path=='/api/update/install':
                    if updates is None: raise ValueError('자동 업데이트를 사용할 수 없습니다.')
                    if not update_lock.acquire(blocking=False): raise ValueError('업데이트를 이미 준비하고 있습니다.')
                    updating.set()
                    try:
                        with lab.lock:
                            if lab.active(): raise ValueError('성능 비교를 마친 뒤 업데이트해 주세요.')
                            if closing.is_set(): raise ValueError('프로그램을 종료하고 있습니다.')
                        result=updates.install()
                        closing.set()
                        try: self.send(result)
                        finally: threading.Thread(target=on_shutdown or self.server.shutdown,daemon=True).start()
                    finally:
                        updating.clear()
                        update_lock.release()
                    return
                routes={
                    '/api/refresh':lambda:lab.refresh(),
                    '/api/config':lambda:lab.select_config(body['path']),
                    '/api/profiles/capture':lambda:lab.capture(body['name'],body.get('notes','')),
                    '/api/profiles/import':lambda:lab.import_profile(body['profile']),
                    '/api/profiles/preview':lambda:lab.preview(body['id']),
                    '/api/profiles/apply':lambda:lab.apply(body['id'],body['configHash']),
                    '/api/backups/restore':lambda:lab.restore(body['id']),
                    '/api/results/scan':lambda:lab.scan(),
                    '/api/results/annotate':lambda:lab.annotate(body['id'],body.get('noiseDbA'),body.get('fanRpm'),body.get('notes','')),
                    '/api/results/link':lambda:lab.link_result(body['id'],body['profileId'],body['mode'],body.get('confirmed',False)),
                    '/api/benchmark/start':lambda:lab.start(body.get('driver','steam'),body.get('cooldownSeconds',120)),
                    '/api/benchmark/cancel':lambda:lab.cancel_run(),
                    '/api/community/prepare':lambda:lab.share_bundle(body['profileId'],body.get('runIds',[]),body.get('author','익명')),
                }
                if path=='/api/shutdown':
                    with lab.lock:
                        if lab.active(): raise ValueError('테스트를 중단하고 원래 모드로 복원한 뒤 종료하세요.')
                        if updating.is_set(): raise ValueError('업데이트 준비가 끝날 때까지 기다려 주세요.')
                        closing.set()
                    self.send({'message':'프로그램이 종료되었습니다.'})
                    threading.Thread(target=on_shutdown or self.server.shutdown,daemon=True).start(); return
                if path not in routes: self.send({'error':'찾을 수 없습니다.'},404); return
                with lab.lock:
                    if closing.is_set(): raise ValueError('프로그램을 종료하고 있습니다.')
                    if updating.is_set() and path=='/api/benchmark/start': raise ValueError('업데이트를 준비하는 중입니다.')
                    result=routes[path]()
                self.send(result)
            except (ValueError,KeyError,TypeError,OSError) as e: self.send({'error':str(e)},400)
            except Exception: self.send({'error':'처리하지 못했습니다. 설정을 변경하지 말고 프로그램을 다시 실행하세요.'},500)
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--show',action='store_true',help='트레이로 시작하지 않고 전용 창을 표시합니다.')
    parser.add_argument('--no-browser',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--ready-file',help=argparse.SUPPRESS)
    args=parser.parse_args()
    assets=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    data=Path(args.data_dir or Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'GHelperProfileLab')
    guard=None
    if not args.no_browser:
        from single_instance import InstanceGuard
        guard=InstanceGuard(data)
        if not guard.acquire_or_signal():
            guard.close()
            return
    server=None
    try:
        lab=Lab(data,assets); token=secrets.token_urlsafe(32); closing=threading.Event()
        host=None
        def shutdown():
            if host: host.finish_exit()
            else: server.shutdown()
        from community import CommunityService
        server=create_server(lab,assets,token,args.port,closing,shutdown,CommunityService(lab),UpdateService(data))
        url=f'http://127.0.0.1:{server.server_port}/?session={token}'
        if args.ready_file:
            from core import atomic_json
            atomic_json(Path(args.ready_file),{'url':url,'pid':os.getpid()})
        if args.no_browser:
            if sys.stdout: print(url,flush=True)
            server.serve_forever(poll_interval=.5)
        else:
            from desktop_shell import DesktopShell
            host=DesktopShell(lab,server,closing,assets,data,guard)
            worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.2},daemon=True)
            worker.start()
            try: host.run(url,show=args.show)
            finally:
                server.shutdown()
                worker.join(timeout=3)
    finally:
        if server: server.server_close()
        if guard: guard.close()

if __name__=='__main__':
    try: main()
    except Exception as e:
        if getattr(sys,'frozen',False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'프로그램을 시작하지 못했습니다.\n'+str(e),'GHelper Profile Lab',0x10)
        else: raise
