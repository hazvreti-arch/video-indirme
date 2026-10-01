import json, os, re, shutil, subprocess
from pathlib import Path
import yt_dlp
from yt_dlp.utils import DownloadError
from platforms_service import detect_platform, normalize_url
from storage_service import job_dir
from queue_service import is_paused
import time
try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None

def _youtube_fallback_options():
    """YouTube fallback using the current mweb client + PO Token provider.

    yt-dlp currently recommends mweb for YouTube GVS requests when a PO Token
    is needed. The bgutil-ytdlp-pot-provider plugin can mint the token through
    its local script provider.
    """
    out = {
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb'],
                'player_skip': ['webpage'],
            },
            'youtubepot-bgutilscript': {
                'server_home': str(Path(__file__).resolve().parent / '.bgutil-ytdlp-pot-provider' / 'server')
            },
        },
    }
    try:
        if shutil.which('deno'):
            out['js_runtimes'] = 'deno'
    except Exception:
        pass
    return out

def _ydl_network_options(url: str):
    """Return yt-dlp network options tuned for browser/WAF-sensitive sites."""
    options = {}
    try:
        platform = detect_platform(url)
        if platform.get('key') == 'tiktok':
            # curl-cffi impersonation is useful for TikTok's browser/WAF checks.
            options['impersonate'] = 'chrome'
    except Exception:
        pass
    return options


def _is_youtube_bot_error(exc):
    text = str(exc).lower()
    markers = (
        'sign in to confirm you’re not a bot',
        "sign in to confirm you're not a bot",
        'confirm you are not a bot',
        'confirm you’re not a bot',
        'webpage request',
        'http error 429',
    )
    return any(marker in text for marker in markers)


def _extract_info(url: str, options: dict):
    normalized = normalize_url(url)
    merged = dict(options or {})
    merged.update(_ydl_network_options(normalized))
    try:
        with yt_dlp.YoutubeDL(merged) as ydl:
            return ydl.extract_info(normalized, download=False)
    except DownloadError as exc:
        try:
            is_youtube = detect_platform(normalized).get('key') == 'youtube'
        except Exception:
            is_youtube = False
        if not is_youtube or not _is_youtube_bot_error(exc):
            raise

        fallback = dict(options or {})
        fallback.update(_youtube_fallback_options())
        with yt_dlp.YoutubeDL(fallback) as ydl:
            return ydl.extract_info(normalized, download=False)

def ffmpeg_bin():
    system = shutil.which('ffmpeg')
    if system:
        return system
    if imageio_ffmpeg:
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise RuntimeError('FFmpeg bulunamadı.')

def probe_file(path):
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return {}
    try:
        r = subprocess.run([ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(path)], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 else {}
    except Exception:
        return {}

def _formats(info):
    seen, result = set(), []
    for f in info.get('formats', []) or []:
        h = f.get('height'); ext = f.get('ext')
        if not h or not ext:
            continue
        key = (h, ext, f.get('fps') or 0)
        if key in seen:
            continue
        seen.add(key)
        result.append({'height': h, 'ext': ext, 'fps': f.get('fps') or 0, 'vcodec': f.get('vcodec'), 'acodec': f.get('acodec'), 'filesize': f.get('filesize') or f.get('filesize_approx') or 0})
    return sorted(result, key=lambda x: (x['height'], x['fps'], x['filesize']), reverse=True)[:80]

def analyze(url, playlist=True):
    url = normalize_url(url)
    info = _extract_info(url, {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': not playlist,
        'skip_download': True,
        'extract_flat': False,
    })
    entries = []
    if info.get('_type') == 'playlist':
        for e in info.get('entries') or []:
            if e:
                entries.append({'id': e.get('id'), 'title': e.get('title') or 'Video', 'url': e.get('webpage_url') or e.get('url'), 'duration': e.get('duration')})
    platform = detect_platform(url)
    return {
        'id': info.get('id'), 'title': info.get('title') or 'Video', 'thumbnail': info.get('thumbnail'),
        'uploader': info.get('uploader') or '', 'channel': info.get('channel') or info.get('uploader') or '',
        'duration': info.get('duration') or 0, 'platform': info.get('extractor_key') or info.get('extractor') or platform['name'],
        'platform_key': platform['key'], 'kind': 'playlist' if info.get('_type') == 'playlist' else 'video',
        'width': info.get('width'), 'height': info.get('height'), 'fps': info.get('fps'), 'vcodec': info.get('vcodec'), 'acodec': info.get('acodec'),
        'abr': info.get('abr'), 'vbr': info.get('vbr'), 'filesize': info.get('filesize') or info.get('filesize_approx'),
        'formats': _formats(info),
        'chapters': [{'start_time': c.get('start_time'), 'end_time': c.get('end_time'), 'title': c.get('title')} for c in info.get('chapters') or []],
        'subtitles': sorted((info.get('subtitles') or {}).keys()),
        'automatic_captions': sorted((info.get('automatic_captions') or {}).keys()),
        'entries': entries,
        'webpage_url': info.get('webpage_url') or url,
        'preview_url': info.get('url') or '',
    }

def thumbnail_download(url, target):
    """Download the best thumbnail URL exposed by yt-dlp and return its local path."""
    from urllib.request import Request, urlopen
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    normalized = normalize_url(url)
    thumb_opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL({**thumb_opts, **_ydl_network_options(normalized)}) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except DownloadError as exc:
        try:
            is_youtube = detect_platform(normalized).get('key') == 'youtube'
        except Exception:
            is_youtube = False
        if not is_youtube or not _is_youtube_bot_error(exc):
            raise
        fallback = dict(thumb_opts)
        fallback.update(_youtube_fallback_options())
        with yt_dlp.YoutubeDL(fallback) as ydl:
            info = ydl.extract_info(normalized, download=False)
    thumb = info.get("thumbnail")
    if not thumb:
        raise RuntimeError("Thumbnail bulunamadı.")
    title = _safe_name(info.get("title") or "thumbnail")
    lower = thumb.split("?", 1)[0].lower()
    ext = ".jpg"
    for candidate in (".png", ".webp", ".jpeg", ".jpg"):
        if lower.endswith(candidate):
            ext = candidate
            break
    out = target / f"{title[:120]}{ext}"
    req = Request(thumb, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=30) as response, open(out, "wb") as fh:
            fh.write(response.read())
    except Exception as exc:
        raise RuntimeError("Thumbnail indirilemedi.") from exc
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("Thumbnail indirilemedi.")
    return out

def _safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]+', ' ', s or 'video')
    return re.sub(r'\s+', ' ', s).strip()[:160] or 'video'

def selector(quality, mode='video', container='mp4'):
    if mode == 'audio':
        return 'bestaudio/best'
    if quality == 'best':
        return 'bestvideo*+bestaudio/best'
    h = {'1080':1080,'720':720,'480':480,'360':360}.get(str(quality),720)
    return f'bestvideo*[height<={h}]+bestaudio/best[height<={h}]/best[height<={h}]'

def render_name(template, title, quality, ext, platform=''):
    values={'title':_safe_name(title),'quality':str(quality),'ext':ext.lstrip('.'),'platform':platform,'date':__import__('datetime').datetime.now().strftime('%Y-%m-%d')}
    name=template or '{title}-{quality}.{ext}'
    for k,v in values.items(): name=name.replace('{'+k+'}', str(v))
    if '.' not in Path(name).name: name += '.'+values['ext']
    return _safe_name(Path(name).stem)+Path(name).suffix


def download(url, job, options, update):
    outdir = job_dir(job.id)
    mode = options.get('mode', 'video')
    quality = str(options.get('quality', '720'))
    container = options.get('container', 'mp4')
    audio_format = options.get('audio_format', 'mp3')
    subtitle_lang = options.get('subtitle_lang') or ''
    subtitle_embed = bool(options.get('subtitle_embed'))
    playlist = bool(options.get('playlist'))
    postprocessors = []
    if mode == 'audio':
        postprocessors.append({'key':'FFmpegExtractAudio','preferredcodec':audio_format,'preferredquality':'320'})
    opts = {
        'format': selector(quality, mode, container),
        'outtmpl': str(outdir / '%(title).100s.%(ext)s'),
        'merge_output_format': container if mode == 'video' and container in {'mp4','webm','mkv'} else None,
        'noplaylist': not playlist, 'quiet': True, 'no_warnings': True, 'progress_hooks': [],
        'restrictfilenames': True, 'retries': 3, 'fragment_retries': 3, 'socket_timeout': 30,
        'postprocessors': postprocessors, 'writesubtitles': bool(subtitle_lang), 'subtitleslangs': [subtitle_lang] if subtitle_lang else None,
        'writeautomaticsub': False, 'embedsubtitles': subtitle_embed if subtitle_lang and mode == 'video' else False,
    }
    opts['ffmpeg_location'] = ffmpeg_bin()
    def hook(d):
        st = d.get('status')
        if st == 'downloading':
            while is_paused(job.id):
                time.sleep(0.5)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0; done = d.get('downloaded_bytes') or 0
            pct = min(99, round(done * 100 / total)) if total else 0
            update(progress=pct, bytes_done=done, bytes_total=total, speed=d.get('_speed_str') or '', eta=d.get('_eta_str') or '', title=d.get('info_dict',{}).get('title') or job.title)
        elif st == 'finished':
            update(progress=100)
    opts['progress_hooks'] = [hook]
    final_opts = {k: v for k, v in opts.items() if v is not None}
    normalized = normalize_url(url)
    final_opts.update(_ydl_network_options(normalized))
    try:
        with yt_dlp.YoutubeDL(final_opts) as ydl:
            info = ydl.extract_info(normalized, download=True)
    except DownloadError as exc:
        try:
            is_youtube = detect_platform(normalized).get('key') == 'youtube'
        except Exception:
            is_youtube = False
        if not is_youtube or not _is_youtube_bot_error(exc):
            raise
        fallback = dict(final_opts)
        fallback.update(_youtube_fallback_options())
        with yt_dlp.YoutubeDL(fallback) as ydl:
            info = ydl.extract_info(normalized, download=True)
    files = [p for p in outdir.rglob('*') if p.is_file() and p.suffix.lower() not in {'.srt','.vtt','.ass','.lrc'}]
    if not files:
        raise RuntimeError('Dosya oluşturulamadı.')
    result = max(files, key=lambda p: p.stat().st_size)
    if any(options.get(k) is not None for k in ('trim_start','trim_end','chapter_start','chapter_end')) and mode == 'video':
        start = options.get('trim_start') if options.get('trim_start') is not None else options.get('chapter_start')
        end = options.get('trim_end') if options.get('trim_end') is not None else options.get('chapter_end')
        result = trim_file(result, start, end, container)
    naming = options.get('naming') or '{title}-{quality}.{ext}'
    try:
        desired = result.with_name(render_name(naming, info.get('title') or job.title, quality, result.suffix, detect_platform(url)['name']))
        if desired != result:
            result.rename(desired); result = desired
    except Exception:
        pass
    update(progress=100, filename=str(result), title=info.get('title') or job.title, platform=detect_platform(url)['name'], meta_json=json.dumps(options, ensure_ascii=False))
    return result

def trim_file(path, start, end, container='mp4'):
    start = max(0, float(start or 0)); out = Path(path).with_name(Path(path).stem + '_clip.' + container)
    cmd = [ffmpeg_bin(), '-y', '-ss', str(start), '-i', str(path)]
    if end is not None: cmd += ['-t', str(max(0.1, float(end)-start))]
    cmd += ['-c','copy',str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        cmd = [ffmpeg_bin(), '-y', '-ss', str(start), '-i', str(path)]
        if end is not None: cmd += ['-t', str(max(0.1, float(end)-start))]
        cmd += ['-c:v','libx264','-preset','veryfast','-c:a','aac',str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0: raise RuntimeError('Klip oluşturulamadı.')
    return out

def convert_file(src, target_ext, mode='video', bitrate='320k'):
    src = Path(src); out = src.with_name(src.stem + '_converted.' + target_ext)
    cmd = [ffmpeg_bin(), '-y', '-i', str(src)]
    if mode == 'audio': cmd += ['-vn','-b:a',bitrate]
    elif target_ext == 'webm': cmd += ['-c:v','libvpx-vp9','-c:a','libopus']
    elif target_ext == 'mkv': cmd += ['-c:v','copy','-c:a','copy']
    else: cmd += ['-c:v','libx264','-preset','veryfast','-c:a','aac']
    cmd += [str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0: raise RuntimeError('Dönüştürme başarısız oldu.')
    return out
