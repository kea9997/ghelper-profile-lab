"""Local profile storage and conservative G-Helper config transactions."""
from __future__ import annotations
import hashlib, json, math, os, re, tempfile, threading, time, uuid, shutil
from datetime import datetime, timezone
from pathlib import Path
import windows_bridge as bridge
from result_reader import parse_result
from updater import APP_VERSION

MODES = {2: '조용', 0: '균형', 1: '터보'}
RANGES = {'limit_total': (0,150), 'limit_slow': (0,150), 'limit_fast': (0,150), 'limit_cpu': (0,150),
          'auto_apply': (0,1), 'auto_apply_power': (0,1), 'auto_boost': (0,6), 'performance': (0,4),
          'gpu_temp': (60,87), 'gpu_power': (0,80), 'gpu_boost': (0,25),
          'gpu_core': (-500,250), 'gpu_memory': (-500,2000), 'gpu_clock_limit': (0,4000)}
FAN = re.compile(r'fan_profile_(cpu|gpu|mid)_([012])$')
KEY = re.compile(r'(.+)_([012])$')
def now(): return datetime.now(timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def known_key(key):
    m=KEY.fullmatch(key)
    return bool(FAN.fullmatch(key) or (m and m[1] in RANGES))
def checked_settings(obj):
    if not isinstance(obj,dict) or len(obj)>120: raise ValueError('프리셋 설정 형식이 올바르지 않습니다.')
    out={}
    for key,val in obj.items():
        if not isinstance(key,str) or not known_key(key): raise ValueError('공유할 수 없는 설정 항목: '+str(key))
        if FAN.fullmatch(key):
            if not isinstance(val,str) or not re.fullmatch(r'[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){15}',val): raise ValueError('팬 곡선 형식 오류: '+key)
            a=list(bytes.fromhex(val.replace('-',' ')))
            if any(v>100 for v in a) or a[:8]!=sorted(a[:8]) or a[8:]!=sorted(a[8:]): raise ValueError('팬 곡선 범위 또는 순서 오류: '+key)
            out[key]=val.upper()
        else:
            lo,hi=RANGES[KEY.fullmatch(key)[1]]
            if type(val) is not int or not lo<=val<=hi: raise ValueError('설정 범위를 확인하세요: '+key)
            out[key]=val
    return out
def tuning(config): return checked_settings({k:v for k,v in config.items() if known_key(k)})
def clean_text(v,limit=200):
    if not isinstance(v,str): raise ValueError('텍스트 형식 오류')
    if len(v)>limit or '\x00' in v: raise ValueError('텍스트가 너무 길거나 잘못되었습니다.')
    return v.strip()
def public_hardware(h):
    if not isinstance(h,dict): raise ValueError('기기 정보가 없습니다.')
    gpu=h.get('gpu',[])
    if not isinstance(gpu,list) or len(gpu)>6: raise ValueError('GPU 정보 형식 오류')
    return {**{k:clean_text(h.get(k,''),200) for k in ('manufacturer','model','cpu','bios')},
            'gpu':[clean_text(g,200) for g in gpu], 'ram_gb':h.get('ram_gb') if isinstance(h.get('ram_gb'),(int,float)) and math.isfinite(h['ram_gb']) and 0<h['ram_gb']<=2048 else None}
def load_json(path,limit=1024*1024):
    raw=Path(path).read_bytes()
    if len(raw)>limit: raise ValueError('파일 크기 제한을 초과했습니다.')
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError('중복 JSON 항목: '+k)
            d[k]=v
        return d
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('비정상 숫자')))
def atomic_json(path,data):
    atomic_bytes(path,json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
def atomic_bytes(path,payload):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.profile-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class Lab:
    def __init__(self,data_dir,assets):
        self.data=Path(data_dir); self.assets=Path(assets); self.data.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock(); self.cancel=threading.Event()
        self.store_file=self.data/'library.json'
        self.db=load_json(self.store_file) if self.store_file.exists() else {'profiles':[], 'runs':[], 'backups':[], 'seen':{}}
        self.prefs=load_json(self.data/'preferences.json') if (self.data/'preferences.json').exists() else {}
        self.hardware=public_hardware(bridge.detect_hardware()); self.discovery=bridge.discover()
        self.benchmark={'status':'idle','message':'3개 모드를 비교할 준비가 되었습니다.','completed':0,'total':3,'mode':None}
        journal=self.data/'benchmark-recovery.json'
        if journal.exists():
            self.benchmark={'status':'recovery','message':'이전 테스트가 중단되었습니다. G-Helper에서 시작 전 모드를 확인하세요.','recovery':load_json(journal),'completed':0,'total':3,'mode':None}
    def save(self): atomic_json(self.store_file,self.db)
    def active(self): return self.benchmark['status'] in ('running','cooling','waiting','restoring','awaiting_stop')
    def require_idle(self):
        if self.active(): raise ValueError('벤치마크 중에는 설정·자료를 변경할 수 없습니다.')
    def config_path(self):
        p=self.prefs.get('config_path') or self.discovery.get('config_path')
        if not p or not Path(p).is_file(): raise ValueError('G-Helper config.json 경로를 선택하세요.')
        return Path(p)
    def config(self):
        d=load_json(self.config_path())
        if not isinstance(d,dict): raise ValueError('G-Helper 설정이 JSON 객체가 아닙니다.')
        return d
    def verified(self): return bool(self.prefs.get('config_path') or self.discovery.get('config_verified'))
    def state(self):
        with self.lock:
            update_status_file=self.data/'update-status.txt'
            try:
                update_status=update_status_file.read_text(encoding='utf-8').strip()
                update_status_file.unlink(missing_ok=True)
            except FileNotFoundError: update_status=None
            if update_status not in ('updated','failed'): update_status=None
            discovery={**self.discovery,'ghelper_running':bridge.ghelper_running()}
            discovery['config_verified']=self.verified()
            try: discovery['config_path']=str(self.config_path()); config=self.config()
            except (OSError,ValueError): config={}
            # Only expose tuning and mode to UI, not hotkey executable paths etc.
            config={k:v for k,v in config.items() if known_key(k) or k=='performance_mode'}
            catalog=load_json(self.assets/'catalog.json') if (self.assets/'catalog.json').exists() else {'entries':[]}
            return {'hardware':self.hardware,'discovery':discovery,'config':config,
                    **{k:self.db[k] for k in ('profiles','runs','backups')},'catalog':catalog,
                    'benchmark':dict(self.benchmark),'communityUrl':'https://ghelper.optiwork.co.kr',
                    'releaseUrl':'https://github.com/kea9997/ghelper-profile-lab/releases/latest','appVersion':APP_VERSION,
                    'updateStatus':update_status}
    def refresh(self):
        self.discovery=bridge.discover(); return self.state()
    def select_config(self,path):
        with self.lock:
            self.require_idle(); p=Path(path).resolve()
            if p.name.lower()!='config.json' or not p.is_file(): raise ValueError('실제 G-Helper config.json 파일을 선택하세요.')
            c=load_json(p)
            if not isinstance(c,dict) or 'performance_mode' not in c: raise ValueError('G-Helper 설정 파일을 확인하세요.')
            self.prefs['config_path']=str(p); atomic_json(self.data/'preferences.json',self.prefs)
            return self.state()
    def _capture(self,name,notes):
        c=self.config(); settings=tuning(c)
        p={'schemaVersion':1,'id':uuid.uuid4().hex,'name':clean_text(name,80) or '내 설정',
           'notes':clean_text(notes,2000),'createdAt':now(),'hardware':self.hardware,
           'ghelperVersion':self.discovery.get('ghelper_version') or 'unknown','settings':settings,
           'settingsHash':digest(settings),'activeMode':c.get('performance_mode'),'origin':'local'}
        self.db['profiles'].insert(0,p); self.save(); return p
    def capture(self,name,notes=''):
        with self.lock: self.require_idle(); return self._capture(name,notes)
    def import_profile(self,obj):
        with self.lock:
            self.require_idle()
            if not isinstance(obj,dict) or obj.get('schemaVersion')!=1: raise ValueError('지원하는 프리셋 파일이 아닙니다.')
            if 'profile' in obj: obj=obj['profile']
            settings=checked_settings(obj.get('settings'))
            if not settings: raise ValueError('적용할 설정이 없습니다. 참고 자료는 프리셋이 아닙니다.')
            if obj.get('settingsHash')!=digest(settings): raise ValueError('설정 해시가 일치하지 않습니다.')
            p={'schemaVersion':1,'id':uuid.uuid4().hex,'name':clean_text(obj.get('name','가져온 설정'),80),
               'notes':clean_text(obj.get('notes',''),2000),'createdAt':now(),
               'hardware':public_hardware(obj.get('hardware')),'ghelperVersion':clean_text(obj.get('ghelperVersion','unknown'),80),
               'settings':settings,'settingsHash':digest(settings),'activeMode':obj.get('activeMode') if obj.get('activeMode') in MODES else None,'origin':'imported'}
            self.db['profiles'].insert(0,p); self.save(); return p
    def profile(self,id):
        p=next((p for p in self.db['profiles'] if p['id']==id),None)
        if p is None: raise ValueError('프리셋을 찾을 수 없습니다.')
        return p
    def preview(self,id):
        p=self.profile(id); c=self.config(); settings=checked_settings(p['settings']); reasons=[]
        for key in ('model','cpu','gpu'):
            a=self.hardware.get(key); b=p['hardware'].get(key)
            if not a or not b or a!=b: reasons.append(key+' 정보가 다릅니다. 이 기기에서 적용할 수 없습니다.')
        if not self.verified(): reasons.append('사용 중인 G-Helper 설정 경로를 먼저 확인하세요.')
        current={k:v for k,v in c.items() if known_key(k)}
        changes=[{'key':k,'before':current.get(k),'after':settings.get(k)} for k in sorted(set(current)|set(settings)) if current.get(k)!=settings.get(k)]
        return {'compatible':not reasons,'reasons':reasons,'changes':changes,'configHash':file_hash(self.config_path()),'settingsHash':digest(settings)}
    def _backup(self,path):
        id=uuid.uuid4().hex; target=self.data/'backups'/f'{id}.json'; target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path,target)
        item={'id':id,'createdAt':now(),'configPath':str(path),'sha256':file_hash(target)}
        self.db['backups'].insert(0,item); self.save(); return item
    def apply(self,id,expected_hash):
        with self.lock:
            self.require_idle(); preview=self.preview(id)
            if not preview['compatible']: raise ValueError(' '.join(preview['reasons']))
            if bridge.ghelper_running(): raise ValueError('G-Helper 트레이 메뉴에서 종료한 뒤 적용하세요. 강제 종료하지 않습니다.')
            if preview['configHash']!=expected_hash: raise ValueError('미리보기 이후 설정이 바뀌었습니다. 다시 확인하세요.')
            path=self.config_path(); c=self.config(); settings=checked_settings(self.profile(id)['settings'])
            merged={k:v for k,v in c.items() if not known_key(k)}; merged.update(settings)
            backup=self._backup(path)
            if bridge.ghelper_running() or file_hash(path)!=expected_hash: raise ValueError('설정이 변경되었거나 G-Helper가 실행됐습니다. 적용을 중단했습니다.')
            atomic_json(path,merged)
            if load_json(path)!=merged: raise ValueError('설정 쓰기 검증에 실패했습니다. 백업으로 복원하세요.')
            return {'message':'설정 파일 저장 완료. G-Helper를 다시 실행하면 반영됩니다.','backupId':backup['id']}
    def restore(self,id):
        with self.lock:
            self.require_idle()
            item=next((b for b in self.db['backups'] if b['id']==id),None)
            if not item: raise ValueError('백업을 찾을 수 없습니다.')
            path=self.config_path(); source=self.data/'backups'/f'{id}.json'
            if str(path)!=item['configPath'] or file_hash(source)!=item['sha256']: raise ValueError('백업 경로나 무결성이 다릅니다.')
            if bridge.ghelper_running(): raise ValueError('G-Helper를 종료한 뒤 복원하세요.')
            c=load_json(source); before=file_hash(path); backup=self._backup(path)
            if bridge.ghelper_running() or file_hash(path)!=before: raise ValueError('복원 중 설정 변경을 감지했습니다.')
            atomic_bytes(path,source.read_bytes())
            return {'message':'백업 복원 완료. G-Helper를 다시 실행하세요.','backupId':backup['id']}
    def result_files(self):
        path=self.discovery.get('results_dir')
        return list(Path(path).glob('*.3dmark-result')) if path and Path(path).is_dir() else []
    def _import_result(self,path,profile=None,mode=None):
        sha=file_hash(path)
        if sha in self.db['seen']: return None
        parsed=parse_result(path)
        if profile:
            raw_target=self.data/'results'/(sha+'.3dmark-result')
            raw_target.parent.mkdir(exist_ok=True)
            if not raw_target.exists(): shutil.copyfile(path,raw_target)
        run={**parsed,'id':uuid.uuid4().hex,'createdAt':now(),'sourceFile':Path(path).name,
             'mode':mode,'profileId':profile['id'] if profile else None,'settingsHash':profile['settingsHash'] if profile else None,
             'binding':'captured' if profile else 'unbound','noiseDbA':None,'fanRpm':None,'notes':''}
        self.db['runs'].insert(0,run); self.db['seen'][sha]=run['id']; self.save(); return run
    def scan(self):
        with self.lock:
            self.require_idle(); added=0
            for p in self.result_files():
                try:
                    if self._import_result(p): added+=1
                except (OSError,ValueError): continue
            return {'added':added,'runs':self.db['runs']}
    def annotate(self,id,noiseDbA=None,fanRpm=None,notes=''):
        with self.lock:
            r=next((r for r in self.db['runs'] if r['id']==id),None)
            if not r: raise ValueError('결과를 찾을 수 없습니다.')
            for name,v,hi in [('noiseDbA',noiseDbA,140),('fanRpm',fanRpm,20000)]:
                if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=hi): raise ValueError('측정값 범위를 확인하세요.')
                r[name]=v
            r['notes']=clean_text(notes,2000); self.save(); return r
    def link_result(self,id,profileId,mode,confirmed=False):
        with self.lock:
            self.require_idle()
            r=next((r for r in self.db['runs'] if r['id']==id),None)
            if not r or r['status']!='valid' or r['binding'] not in ('unbound','manual'):
                raise ValueError('직접 실행한 정상 결과만 설정에 연결할 수 있습니다.')
            p=self.profile(profileId)
            if p.get('origin')!='local' or p.get('hardware')!=self.hardware:
                raise ValueError('이 컴퓨터에서 직접 저장한 설정을 선택하세요.')
            if type(mode) is not int or mode not in MODES or confirmed is not True:
                raise ValueError('측정 당시 사용한 설정과 모드를 확인해 주세요.')
            r.update({'mode':mode,'profileId':p['id'],'settingsHash':p['settingsHash'],
                      'binding':'manual','manuallyLinkedAt':now()})
            self.save(); return r
    def share_bundle(self,profileId,runIds,author):
        with self.lock:
            p=self.profile(profileId)
            if not isinstance(runIds,list) or len(runIds)>20: raise ValueError('최대 20개의 결과를 선택하세요.')
            runs=[]
            for id in runIds:
                r=next((r for r in self.db['runs'] if r['id']==id),None)
                if not r or r['binding'] not in ('captured','manual') or r['settingsHash']!=p['settingsHash'] or r['status']!='valid' or r['mode'] not in MODES or (r['binding']=='manual' and r['profileId']!=p['id']): raise ValueError('이 설정에 연결한 정상 결과만 공유할 수 있습니다.')
                public_run={k:r.get(k) for k in ('totalScore','graphicsScore','cpuScore','mode','createdAt','noiseDbA','fanRpm','notes','settingsHash')}
                if r['binding']=='manual':
                    marker='[직접 연결 · 측정 당시 설정 미검증]'
                    public_run['notes']=marker+' '+r['notes'][:2000-len(marker)-1]
                runs.append(public_run)
            profile={k:p[k] for k in ('schemaVersion','name','notes','hardware','ghelperVersion','settings','settingsHash','activeMode')}
            return {'schemaVersion':1,'kind':'ghelper-profile-share','author':clean_text(author,40) or '익명', 'profile':profile,'runs':runs,'verification':'user-reported'}
    def start(self,driver,cooldownSeconds):
        with self.lock:
            self.require_idle()
            if driver not in ('steam','guided','enterprise'): raise ValueError('실행 방식을 선택하세요.')
            if not self.verified(): raise ValueError('G-Helper 설정 경로를 먼저 확인하세요.')
            if bridge.ac_connected() is not True: raise ValueError('충전기 연결을 확인할 수 없습니다. 연결 후 다시 시도하세요.')
            if bridge.get_benchmark_running(): raise ValueError('이미 실행 중인 벤치마크가 있습니다.')
            if not bridge.ghelper_running(): raise ValueError('G-Helper를 먼저 실행하세요.')
            if driver=='enterprise' and not self.discovery.get('cli_exe'): raise ValueError('공식 Enterprise CLI를 찾을 수 없습니다. Steam판 자동 실행을 선택하세요.')
            if driver in ('steam','guided') and not self.discovery.get('benchmark_exe'): raise ValueError('3DMark 설치를 찾지 못했습니다.')
            if driver=='steam' and Path(self.discovery['benchmark_exe']).name.lower()!='3dmark.exe': raise ValueError('Steam판 자동 실행에는 3DMark.exe가 필요합니다. 직접 실행을 선택하세요.')
            if type(cooldownSeconds) is not int or not 30<=cooldownSeconds<=600: raise ValueError('대기 시간은 30~600초로 지정하세요.')
            original=self.config().get('performance_mode')
            if original not in MODES: raise ValueError('기본 조용/균형/터보 모드에서 시작하세요.')
            self.cancel.clear(); self.benchmark={'status':'running','message':'준비 중','completed':0,'total':3,'mode':None,'sessionId':uuid.uuid4().hex,'driver':driver,'engineRunning':False,'cooldownUntil':None}
            atomic_json(self.data/'benchmark-recovery.json',{'originalMode':original,'createdAt':now()})
            threading.Thread(target=self._benchmark,args=(driver,cooldownSeconds,original),daemon=True).start()
            return dict(self.benchmark)
    def _status(self,**kw):
        with self.lock: self.benchmark.update(kw)
    def cancel_run(self): self.cancel.set(); return dict(self.benchmark)
    def _benchmark(self,driver,cooldown,original):
        failed=None
        try:
            for index,mode in enumerate((2,0,1)):
                if self.cancel.is_set(): break
                if bridge.ac_connected() is not True: raise ValueError('충전기 연결이 해제되었습니다.')
                self._status(status='running',mode=mode,message=MODES[mode]+' 모드 전환 확인 중')
                bridge.switch_mode(mode,str(self.config_path()))
                self._status(status='cooling',engineRunning=False,cooldownUntil=time.time()+cooldown,message=f'{MODES[mode]} 모드 준비 중 · {cooldown}초 동안 기다립니다.')
                if self.cancel.wait(cooldown): break
                with self.lock: profile=self._capture(MODES[mode]+' · '+datetime.now().strftime('%m/%d %H:%M'),'벤치마크 시작 시 자동 저장')
                before={str(p):(p.stat().st_mtime_ns,p.stat().st_size) for p in self.result_files()}
                out=self.data/'results'/f'{uuid.uuid4().hex}.3dmark-result'; out.parent.mkdir(exist_ok=True)
                self._status(status='waiting',cooldownUntil=None,engineRunning=False,message=('3DMark에서 Time Spy 기본 테스트를 자동으로 여는 중입니다.' if driver=='steam' else '3DMark에서 Time Spy 기본 테스트의 실행 버튼을 눌러주세요.' if driver=='guided' else 'Time Spy 실행 중 · 결과를 기다립니다.'))
                proc=(bridge.start_benchmark(driver,self.discovery,str(out),cancel_event=self.cancel)
                      if driver=='steam' else bridge.start_benchmark(driver,self.discovery,str(out)))
                self._status(message='Time Spy 실행 중 · 결과를 기다립니다.' if driver!='guided' else '3DMark에서 Time Spy 기본 테스트의 실행 버튼을 눌러주세요. 결과 저장 후 다음 모드로 진행합니다.')
                deadline=time.monotonic()+1800; result=None; stable={}; saw_engine=False
                while time.monotonic()<deadline:
                    if self.cancel.wait(2): break
                    if bridge.ac_connected() is not True: raise ValueError('충전기가 분리되었습니다. 테스트를 중단하고 원래 모드를 복원합니다.')
                    c=self.config()
                    if c.get('performance_mode')!=mode or digest(tuning(c))!=profile['settingsHash']: raise ValueError('테스트 도중 모드 또는 설정이 바뀌었습니다. 결과를 설정과 연결하지 않습니다.')
                    engine_running=bridge.get_benchmark_running()
                    self._status(engineRunning=engine_running)
                    saw_engine=saw_engine or engine_running
                    if proc and proc.poll() not in (None,0): raise ValueError('3DMark 실행이 실패했습니다. CLI 라이선스와 설치를 확인하세요.')
                    candidates=([out] if out.exists() else []) if driver=='enterprise' else self.result_files()
                    for p in candidates:
                        stat=p.stat(); sig=(stat.st_mtime_ns,stat.st_size)
                        if str(p) in before and before[str(p)]==sig: continue
                        if stable.get(str(p))!=sig: stable[str(p)]=sig; continue
                        if engine_running or (driver in ('steam','guided') and not saw_engine): continue
                        c=self.config()
                        if c.get('performance_mode')!=mode or digest(tuning(c))!=profile['settingsHash']: raise ValueError('테스트 도중 모드 또는 설정이 바뀌었습니다. 결과를 설정과 연결하지 않습니다.')
                        try:
                            with self.lock: result=self._import_result(p,profile,mode)
                        except (ValueError,OSError): continue
                        if result: break
                    if result: break
                if self.cancel.is_set(): break
                if not result: raise ValueError('30분 내에 새 Time Spy 결과를 확인하지 못했습니다.')
                if result['status']!='valid': raise ValueError('테스트가 정상 점수를 생성하지 못했습니다.')
                self._status(completed=index+1)
        except Exception as exc: failed=str(exc)
        finally:
            try:
                while bridge.get_benchmark_running():
                    self._status(status='awaiting_stop',message='3DMark 테스트를 종료해주세요. 테스트가 멈춘 뒤 원래 모드로 복원합니다.'); time.sleep(3)
                self._status(status='restoring',engineRunning=False,cooldownUntil=None,message='시작 전 모드로 복원 중')
                bridge.switch_mode(original,str(self.config_path()))
                (self.data/'benchmark-recovery.json').unlink(missing_ok=True)
                self._status(status='failed' if failed else 'cancelled' if self.cancel.is_set() else 'complete',message=failed or ('중단 완료 · 원래 모드 복원' if self.cancel.is_set() else '3개 모드 비교 완료 · 원래 모드 복원'))
            except Exception as exc:
                self._status(status='recovery',message=(failed+' / ' if failed else '')+'자동 복원 실패. G-Helper에서 원래 모드('+MODES[original]+')를 선택하세요. '+str(exc))
