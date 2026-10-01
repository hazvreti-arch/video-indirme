import base64, hashlib, json, os, re, secrets, time
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, session, send_file, redirect, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
try:
    import qrcode
except Exception:
    qrcode = None

from config import DATABASE_URL, SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, PUBLIC_BASE_URL, MAX_BATCH_ITEMS, RATE_LIMIT_PER_MINUTE, DOWNLOAD_DIR
from models import db, User, Job, History, Profile, APIKey, Ban, ShareLink, utcnow
from auth_service import current_user, login_user, logout_user, is_banned
from platforms_service import normalize_url, detect_platform, content_kind
from media_service import analyze, download as media_download, convert_file, trim_file, probe_file, thumbnail_download, ffmpeg_bin
from queue_service import submit, pause as pause_job, resume as resume_job
from sharing_service import create_share, hash_token
from storage_service import cleanup_files

app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent), static_folder=str(None))
app.config.update(SECRET_KEY=SECRET_KEY, SQLALCHEMY_DATABASE_URI=DATABASE_URL, SQLALCHEMY_TRACK_MODIFICATIONS=False, JSON_SORT_KEYS=False, MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024)
db.init_app(app)
CORS(app, resources={r'/api/*': {'origins': '*'}})
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[f'{RATE_LIMIT_PER_MINUTE} per minute'])


def json_or_form():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


def safe_json(text, default=None):
    try: return json.loads(text) if text else (default if default is not None else {})
    except Exception: return default if default is not None else {}


def create_app():
    with app.app_context():
        db.create_all()
        bootstrap_admin()
    return app


def bootstrap_admin():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD: return
    u = User.query.filter_by(email=ADMIN_EMAIL).first()
    if not u:
        u=User(email=ADMIN_EMAIL, role='admin'); u.set_password(ADMIN_PASSWORD); db.session.add(u); db.session.commit()
    elif u.role != 'admin':
        u.role='admin'; db.session.commit()


def blocked():
    return is_banned(request.headers.get('X-Forwarded-For', request.remote_addr or ''))


def api_key_user():
    raw=request.headers.get('X-API-Key','').strip()
    if not raw or not raw.startswith('vk_live_'): return None
    h=hashlib.sha256(raw.encode()).hexdigest()
    row=APIKey.query.filter_by(key_hash=h, revoked=False).first()
    if not row: return None
    row.last_used_at=utcnow(); db.session.commit(); return db.session.get(User,row.user_id)


def auth_user(required=False):
    u=current_user() or api_key_user()
    if required and (not u or u.disabled): return None
    return u


def login_page():
    return render_template('login.html')


def register_page():
    return render_template('register.html')

@app.before_request
def before_request():
    if blocked() and not request.path.startswith('/api/admin'):
        return jsonify({'error':'Erişim kısıtlandı.'}),403

@app.context_processor
def inject_user():
    u=current_user()
    return {'current_user':u}

@app.get('/')
def home(): return render_template('index.html')

@app.get('/login')
def login_view(): return login_page()

@app.post('/login')
@limiter.limit('10 per minute')
def login_post():
    d=json_or_form(); email=(d.get('email') or '').strip().lower(); pw=d.get('password') or ''
    u=User.query.filter_by(email=email).first()
    if not u or u.disabled or not u.check_password(pw):
        return jsonify({'error':'E-posta veya şifre hatalı.'}),401
    login_user(u); return jsonify({'ok':True,'redirect':'/'})

@app.get('/register')
def register_view(): return register_page()

@app.post('/register')
@limiter.limit('5 per minute')
def register_post():
    d=json_or_form(); email=(d.get('email') or '').strip().lower(); pw=d.get('password') or ''
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email): return jsonify({'error':'Geçerli bir e-posta gir.'}),400
    if len(pw)<8: return jsonify({'error':'Şifre en az 8 karakter olmalı.'}),400
    if User.query.filter_by(email=email).first(): return jsonify({'error':'Bu hesap zaten var.'}),409
    u=User(email=email); u.set_password(pw); db.session.add(u); db.session.commit(); login_user(u)
    return jsonify({'ok':True,'redirect':'/'})

@app.post('/logout')
def logout(): logout_user(); return jsonify({'ok':True})

@app.get('/api/me')
def me():
    u=current_user()
    return jsonify({'authenticated':bool(u),'user':({'id':u.id,'email':u.email,'role':u.role} if u else None)})

@app.get('/api/health')
def health():
    return jsonify({'ok':True,'version':'4.4','database':bool(db.engine),'worker':'threadpool','timestamp':int(time.time())})

@app.post('/api/analyze')
@limiter.limit('30 per minute')
def api_analyze():
    d=json_or_form(); url=(d.get('url') or '').strip(); playlist=bool(d.get('playlist',True))
    if not url: return jsonify({'error':'Bir bağlantı gir.'}),400
    if len(url)>4000: return jsonify({'error':'Bağlantı çok uzun.'}),400
    try:
        meta=analyze(url,playlist=playlist)
        # Adaptive recommendation: prioritize <=720p for mobile unless only larger formats exist.
        heights=[f['height'] for f in meta.get('formats',[])]
        rec='720' if 720 in heights else ('1080' if 1080 in heights else (str(max(heights)) if heights else 'best'))
        meta['recommended']={'quality':rec,'container':'mp4','reason':'Uyumluluk ve kalite dengesi'}
        return jsonify(meta)
    except Exception as e:
        return jsonify({'error':'İçerik analiz edilemedi: '+str(e)[:300]}),400

@app.post('/api/info')
def api_info_compat(): return api_analyze()


def new_job(url, user, kind='download', options=None):
    options=options or {}; jid=secrets.token_hex(16)
    meta={'options':options}
    j=Job(id=jid,user_id=user.id if user else None,ip=request.remote_addr,url=normalize_url(url),kind=kind,status='queued',meta_json=json.dumps(meta,ensure_ascii=False))
    db.session.add(j); db.session.commit();
    submit(app,jid,media_download,options)
    return j

@app.post('/api/download')
@limiter.limit('12 per minute')
def api_download():
    d=json_or_form(); url=(d.get('url') or '').strip(); user=auth_user(False)
    if not url: return jsonify({'error':'Bir bağlantı gir.'}),400
    options={'quality':str(d.get('quality') or '720'),'container':d.get('container') or 'mp4','mode':d.get('mode') or 'video','audio_format':d.get('audio_format') or 'mp3','subtitle_lang':d.get('subtitle_lang') or '', 'subtitle_embed':bool(d.get('subtitle_embed')), 'playlist':bool(d.get('playlist')), 'naming':d.get('naming') or '{title}-{quality}.{ext}'}
    if options['quality'] not in {'1080','720','480','360','best'}: return jsonify({'error':'Geçersiz kalite.'}),400
    j=new_job(url,user,'download',options)
    return jsonify({'job_id':j.id,'status':j.status})

@app.get('/api/status/<job_id>')
def api_status(job_id):
    j=db.session.get(Job,job_id)
    if not j: return jsonify({'error':'İş bulunamadı.'}),404
    out={k:getattr(j,k) for k in ['id','status','progress','title','platform','filename','error','bytes_done','bytes_total','speed','eta','created_at','updated_at']}
    if j.filename and j.status=='ready': out['download_url']=url_for('api_file',job_id=j.id)
    return jsonify(out)

@app.get('/api/events/<job_id>')
def api_events(job_id):
    def stream():
        last=''
        for _ in range(3600):
            j=db.session.get(Job,job_id)
            if not j: break
            payload={'id':j.id,'status':j.status,'progress':j.progress,'title':j.title,'bytes_done':j.bytes_done,'bytes_total':j.bytes_total,'speed':j.speed,'eta':j.eta,'error':j.error,'download_url':url_for('api_file',job_id=j.id) if j.filename and j.status=='ready' else None}
            raw=json.dumps(payload,ensure_ascii=False)
            if raw!=last:
                yield 'data: '+raw+'\n\n'; last=raw
            if j.status in {'ready','error','cancelled'}: break
            time.sleep(1)
    return Response(stream(),mimetype='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/jobs/<job_id>/pause')
def api_pause(job_id):
    j=db.session.get(Job,job_id)
    if not j: return jsonify({'error':'İş bulunamadı.'}),404
    pause_job(job_id); j.status='paused'; db.session.commit(); return jsonify({'ok':True,'status':'paused'})

@app.post('/api/jobs/<job_id>/resume')
def api_resume(job_id):
    j=db.session.get(Job,job_id)
    if not j: return jsonify({'error':'İş bulunamadı.'}),404
    resume_job(job_id); j.status='downloading'; db.session.commit(); return jsonify({'ok':True,'status':'downloading'})

@app.post('/api/jobs/bulk/<action>')
def api_bulk_jobs(action):
    if action not in {'pause','resume','cancel'}: return jsonify({'error':'Geçersiz action.'}),400
    rows=Job.query.filter(Job.status.in_(['queued','downloading','paused'])).all()
    for j in rows:
        if action=='pause': pause_job(j.id); j.status='paused'
        elif action=='resume': resume_job(j.id); j.status='downloading'
        else: j.status='cancelled'
    db.session.commit(); return jsonify({'ok':True,'count':len(rows),'action':action})

@app.post('/api/jobs/<job_id>/cancel')
def api_cancel(job_id):
    j=db.session.get(Job,job_id)
    if not j: return jsonify({'error':'İş bulunamadı.'}),404
    j.status='cancelled'; db.session.commit(); return jsonify({'ok':True})

@app.get('/api/file/<job_id>')
def api_file(job_id):
    j=db.session.get(Job,job_id)
    if not j or j.status!='ready' or not j.filename: return jsonify({'error':'Dosya hazır değil.'}),404
    p=Path(j.filename)
    if not p.exists(): return jsonify({'error':'Dosya artık mevcut değil.'}),404
    return send_file(p,as_attachment=True,download_name=p.name)

@app.post('/api/convert')
@limiter.limit('8 per minute')
def api_convert():
    f=request.files.get('file')
    if not f or not f.filename: return jsonify({'error':'Bir dosya seç.'}),400
    target=(request.form.get('target') or 'mp4').lower(); mode=request.form.get('mode') or 'video'
    if target not in {'mp4','webm','mkv','mov','mp3','m4a','wav','aac','opus'}: return jsonify({'error':'Desteklenmeyen format.'}),400
    temp=DOWNLOAD_DIR/'uploads'; temp.mkdir(parents=True,exist_ok=True); src=temp/(secrets.token_hex(8)+'_'+secure_filename(f.filename)); f.save(src)
    try:
        ext = target if mode=='audio' else target
        out=convert_file(src,ext,mode=mode)
        return jsonify({'ok':True,'filename':out.name,'download_url':url_for('local_file',name=out.name)})
    except Exception as e:
        return jsonify({'error':str(e)[:300]}),400

@app.get('/api/local-file/<name>')
def local_file(name):
    safe=secure_filename(name); matches=list(DOWNLOAD_DIR.rglob(safe))
    return send_file(matches[0],as_attachment=True,download_name=matches[0].name) if matches else (jsonify({'error':'Dosya bulunamadı.'}),404)

@app.post('/api/clip')
@limiter.limit('8 per minute')
def api_clip():
    f=request.files.get('file')
    if not f: return jsonify({'error':'Video dosyası seç.'}),400
    try:
        start=float(request.form.get('start','0')); end=request.form.get('end'); end=float(end) if end not in (None,'') else None
    except ValueError: return jsonify({'error':'Zaman aralığı geçersiz.'}),400
    temp=DOWNLOAD_DIR/'uploads'; temp.mkdir(parents=True,exist_ok=True); src=temp/(secrets.token_hex(8)+'_'+secure_filename(f.filename)); f.save(src)
    try:
        out=trim_file(src,start,end,(src.suffix.lstrip('.') or 'mp4')); return jsonify({'ok':True,'download_url':url_for('local_file',name=out.name),'filename':out.name})
    except Exception as e: return jsonify({'error':str(e)[:300]}),400

@app.post('/api/batch')
def api_batch():
    d=json_or_form(); raw=d.get('urls') or ''; urls=[normalize_url(x.strip()) for x in raw.splitlines() if x.strip()]
    if not urls: return jsonify({'error':'En az bir URL gir.'}),400
    if len(urls)>MAX_BATCH_ITEMS: return jsonify({'error':f'En fazla {MAX_BATCH_ITEMS} URL.'}),400
    user=auth_user(False); created=[]
    for u in urls:
        j=new_job(u,user,'batch',{'quality':str(d.get('quality') or '720'),'container':d.get('container') or 'mp4','mode':d.get('mode') or 'video'})
        created.append(j.id)
    return jsonify({'job_ids':created,'count':len(created)})

@app.post('/api/playlist')
def api_playlist():
    d=json_or_form(); url=d.get('url') or ''
    try:
        meta=analyze(url,playlist=True); return jsonify({'title':meta.get('title'),'entries':meta.get('entries',[])})
    except Exception as e: return jsonify({'error':str(e)[:300]}),400

@app.post('/api/thumbnail')
def api_thumbnail():
    d=json_or_form(); url=d.get('url') or ''
    target=DOWNLOAD_DIR/'thumbnails'; target.mkdir(parents=True,exist_ok=True)
    try:
        out=thumbnail_download(url,target); return jsonify({'download_url':url_for('local_file',name=out.name),'filename':out.name})
    except Exception as e: return jsonify({'error':str(e)[:300]}),400

@app.post('/api/subtitles')
@limiter.limit('10 per minute')
def api_subtitles():
    d=json_or_form(); url=normalize_url(d.get('url') or ''); lang=(d.get('lang') or '').strip(); fmt=(d.get('format') or 'srt').lower()
    if not url or not lang: return jsonify({'error':'URL ve altyazı dili gerekli.'}),400
    if fmt not in {'srt','vtt'}: return jsonify({'error':'Format SRT veya VTT olmalı.'}),400
    target=DOWNLOAD_DIR/'subtitles'/secrets.token_hex(8); target.mkdir(parents=True,exist_ok=True)
    try:
        import yt_dlp
        opts={'quiet':True,'no_warnings':True,'skip_download':True,'writesubtitles':True,'writeautomaticsub':False,'subtitleslangs':[lang],'subtitlesformat':fmt,'outtmpl':str(target/'%(title).100s.%(ext)s')}
        with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=True)
        files=[x for x in target.iterdir() if x.is_file() and x.suffix.lower()=='.'+fmt]
        if not files: raise RuntimeError('Altyazı bulunamadı.')
        out=files[0]; return jsonify({'ok':True,'filename':out.name,'download_url':url_for('local_file',name=out.name)})
    except Exception as e: return jsonify({'error':str(e)[:300]}),400

@app.post('/api/metadata')
@limiter.limit('8 per minute')
def api_metadata():
    f=request.files.get('file')
    if not f: return jsonify({'error':'Bir medya dosyası seç.'}),400
    temp=DOWNLOAD_DIR/'uploads'; temp.mkdir(parents=True,exist_ok=True)
    src=temp/(secrets.token_hex(8)+'_'+secure_filename(f.filename)); f.save(src)
    d=request.form
    title=d.get('title') or ''; artist=d.get('artist') or ''; album=d.get('album') or ''; genre=d.get('genre') or ''; year=d.get('year') or ''
    out=src.with_name(src.stem+'_tagged'+src.suffix)
    try:
        cmd=[ffmpeg_bin(),'-y','-i',str(src),'-map','0','-c','copy']
        for k,v in {'title':title,'artist':artist,'album':album,'genre':genre,'date':year}.items():
            if v: cmd += ['-metadata',f'{k}={v}']
        cmd += [str(out)]
        import subprocess
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
        if r.returncode!=0: raise RuntimeError('Metadata düzenlenemedi.')
        return jsonify({'ok':True,'filename':out.name,'download_url':url_for('local_file',name=out.name)})
    except Exception as e: return jsonify({'error':str(e)[:300]}),400

@app.get('/api/qr')
def api_qr():
    data=request.args.get('data','').strip()
    if not data: return jsonify({'error':'QR verisi gerekli.'}),400
    if not qrcode: return jsonify({'error':'QR modülü hazır değil.'}),500
    import io
    img=qrcode.make(data); buf=io.BytesIO(); img.save(buf,format='PNG'); buf.seek(0)
    return send_file(buf,mimetype='image/png',download_name='vidora-qr.png')

@app.get('/api/history')
def api_history():
    u=auth_user(False); q=History.query.filter_by(user_id=u.id) if u else History.query.filter_by(user_id=None); rows=q.order_by(History.created_at.desc()).limit(100).all()
    return jsonify([{'id':r.id,'job_id':r.job_id,'title':r.title,'url':r.url,'kind':r.kind,'quality':r.quality,'format':r.format,'filename':r.filename,'download_url':(url_for('api_file',job_id=r.job_id) if r.job_id and db.session.get(Job,r.job_id) and db.session.get(Job,r.job_id).status=='ready' else None),'created_at':r.created_at} for r in rows])

@app.post('/api/history/clear')
def clear_history():
    u=auth_user(False); q=History.query.filter_by(user_id=u.id) if u else History.query.filter_by(user_id=None); q.delete(); db.session.commit(); return jsonify({'ok':True})

@app.get('/api/profiles')
def get_profiles():
    u=auth_user(True)
    if not u: return jsonify({'error':'Giriş gerekli.'}),401
    rows=Profile.query.filter_by(user_id=u.id).order_by(Profile.created_at.desc()).all(); return jsonify([{'id':r.id,'name':r.name,'settings':safe_json(r.settings_json)} for r in rows])

@app.post('/api/profiles')
def create_profile():
    u=auth_user(True)
    if not u: return jsonify({'error':'Giriş gerekli.'}),401
    d=json_or_form(); name=(d.get('name') or 'Preset').strip()[:80]; settings=d.get('settings') or {}
    if isinstance(settings,str): settings=safe_json(settings,{})
    r=Profile(user_id=u.id,name=name,settings_json=json.dumps(settings,ensure_ascii=False)); db.session.add(r); db.session.commit(); return jsonify({'id':r.id,'name':r.name,'settings':settings})

@app.delete('/api/profiles/<int:pid>')
def delete_profile(pid):
    u=auth_user(True); r=db.session.get(Profile,pid)
    if not u or not r or r.user_id!=u.id: return jsonify({'error':'Bulunamadı.'}),404
    db.session.delete(r); db.session.commit(); return jsonify({'ok':True})

@app.post('/api/share/<job_id>')
def share_job(job_id):
    j=db.session.get(Job,job_id)
    if not j or j.status!='ready': return jsonify({'error':'Dosya hazır değil.'}),404
    d=json_or_form(); hours=max(1,min(72,int(d.get('hours') or 1))); max_downloads=max(1,min(100,int(d.get('max_downloads') or 10)))
    row,raw=create_share(j.id,hours,max_downloads); db.session.add(row); db.session.commit(); base=PUBLIC_BASE_URL or request.url_root.rstrip('/'); link=f'{base}/share/{row.id}/{raw}'
    return jsonify({'url':link,'expires_at':row.expires_at,'max_downloads':row.max_downloads})

@app.get('/share/<share_id>/<token>')
def public_share(share_id,token):
    row=ShareLink.query.filter_by(id=share_id,token_hash=hash_token(token)).first()
    if not row or row.expires_at < utcnow() or row.downloads >= row.max_downloads: return jsonify({'error':'Paylaşım bağlantısı geçersiz veya süresi dolmuş.'}),404
    j=db.session.get(Job,row.job_id)
    if not j or j.status!='ready' or not j.filename: return jsonify({'error':'Dosya hazır değil.'}),404
    row.downloads+=1; db.session.commit(); return send_file(j.filename,as_attachment=True,download_name=Path(j.filename).name)

@app.post('/api/keys')
def create_api_key():
    u=auth_user(True)
    if not u: return jsonify({'error':'Giriş gerekli.'}),401
    raw=APIKey.create_raw(); row=APIKey(user_id=u.id,prefix=raw[:16],key_hash=hashlib.sha256(raw.encode()).hexdigest()); db.session.add(row); db.session.commit(); return jsonify({'key':raw,'id':row.id})

@app.get('/api/keys')
def list_api_keys():
    u=auth_user(True)
    if not u: return jsonify({'error':'Giriş gerekli.'}),401
    return jsonify([{'id':x.id,'prefix':x.prefix,'created_at':x.created_at,'revoked':x.revoked,'last_used_at':x.last_used_at} for x in APIKey.query.filter_by(user_id=u.id).all()])

@app.delete('/api/keys/<int:kid>')
def revoke_api_key(kid):
    u=auth_user(True); row=db.session.get(APIKey,kid)
    if not u or not row or row.user_id!=u.id: return jsonify({'error':'Bulunamadı.'}),404
    row.revoked=True; db.session.commit(); return jsonify({'ok':True})

@app.get('/api/v1/analyze')
def v1_analyze():
    if not api_key_user(): return jsonify({'error':'API key gerekli.'}),401
    if request.args.get('url') and not request.is_json and not request.form:
        data = {'url': request.args.get('url'), 'playlist': request.args.get('playlist', 'true').lower() not in {'0','false','no'}}
        with app.test_request_context('/api/analyze', method='POST', json=data):
            return api_analyze()
    return api_analyze()

@app.post('/api/v1/download')
def v1_download():
    if not api_key_user(): return jsonify({'error':'API key gerekli.'}),401
    return api_download()

@app.get('/api/v1/status/<job_id>')
def v1_status(job_id):
    if not api_key_user(): return jsonify({'error':'API key gerekli.'}),401
    return api_status(job_id)

@app.get('/api/admin/stats')
def admin_stats():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    return jsonify({'users':User.query.count(),'jobs':Job.query.count(),'active_jobs':Job.query.filter(Job.status.in_(['queued','downloading'])).count(),'downloads':History.query.count(),'errors':Job.query.filter_by(status='error').count(),'bans':Ban.query.count()})

@app.get('/api/admin/jobs')
def admin_jobs():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    rows=Job.query.order_by(Job.created_at.desc()).limit(200).all(); return jsonify([{'id':j.id,'status':j.status,'progress':j.progress,'title':j.title,'platform':j.platform,'ip':j.ip,'created_at':j.created_at,'speed':j.speed,'error':j.error} for j in rows])

@app.post('/api/admin/ban')
def admin_ban():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    d=json_or_form(); ip=(d.get('ip') or '').strip(); reason=d.get('reason') or ''
    if not ip: return jsonify({'error':'IP gir.'}),400
    if not Ban.query.filter_by(ip=ip).first(): db.session.add(Ban(ip=ip,reason=reason)); db.session.commit()
    return jsonify({'ok':True})

@app.post('/api/admin/unban')
def admin_unban():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    d=json_or_form(); row=Ban.query.filter_by(ip=(d.get('ip') or '').strip()).first()
    if row: db.session.delete(row); db.session.commit()
    return jsonify({'ok':True})

@app.get('/admin')
def admin_page():
    u=current_user()
    if not u or u.role!='admin': return redirect(url_for('login_view'))
    return render_template('admin.html')

@app.get('/api')
def api_page(): return render_template('api.html')

@app.post('/api/admin/cleanup')
def admin_cleanup():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    cleanup_files(); return jsonify({'ok':True})

@app.post('/api/admin/diagnostics')
def diagnostics():
    u=current_user()
    if not u or u.role!='admin': return jsonify({'error':'Yetkisiz.'}),403
    from media_service import ffmpeg_bin
    try: ff=ffmpeg_bin(); ff_ok=True
    except Exception: ff=''; ff_ok=False
    return jsonify({'flask':True,'database':True,'ffmpeg':ff_ok,'ffmpeg_path':ff,'redis':bool(os.getenv('REDIS_URL')),'pwa':True,'queue':'threadpool','storage':str(DOWNLOAD_DIR)})

@app.errorhandler(413)
def too_large(_): return jsonify({'error':'Dosya çok büyük.'}),413

create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT','10000')), debug=False)


ASSETS = {
    "app.css": "app.css",
    "frontend.js": "frontend.js",
    "tools.js": "tools.js",
    "settings.js": "settings.js",
    "library.js": "library.js",
    "sw.js": "sw.js",
    "manifest.json": "manifest.json",
    "icon.svg": "icon.svg",
    "icon-192.png": "icon-192.png",
    "icon-512.png": "icon-512.png",
}

@app.get("/assets/<path:filename>")
def assets(filename):
    name = ASSETS.get(filename)
    if not name:
        return jsonify({"error": "Asset bulunamadı."}), 404
    return send_file(Path(__file__).resolve().parent / name)
