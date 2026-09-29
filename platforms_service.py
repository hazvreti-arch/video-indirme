from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

PLATFORMS = {
    'youtube': ('YouTube', ['youtube.com', 'youtu.be', 'youtube-nocookie.com']),
    'tiktok': ('TikTok', ['tiktok.com']),
    'instagram': ('Instagram', ['instagram.com']),
    'x': ('X', ['x.com', 'twitter.com']),
    'facebook': ('Facebook', ['facebook.com', 'fb.watch']),
    'reddit': ('Reddit', ['reddit.com', 'redd.it']),
    'twitch': ('Twitch', ['twitch.tv']),
    'vimeo': ('Vimeo', ['vimeo.com']),
}

def normalize_url(url: str) -> str:
    url = (url or '').strip()
    parsed = urlparse(url if '://' in url else 'https://' + url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'}]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, parsed.params, urlencode(query), parsed.fragment))

def detect_platform(url: str):
    host = urlparse(normalize_url(url)).netloc.lower().split(':')[0]
    if host.startswith('www.'):
        host = host[4:]
    for key, (label, domains) in PLATFORMS.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return {'key': key, 'name': label}
    return {'key': 'generic', 'name': 'Video'}

def content_kind(url: str):
    low = (url or '').lower()
    if 'list=' in low or 'playlist' in low:
        return 'playlist'
    if '/shorts/' in low:
        return 'short'
    if '/live' in low:
        return 'live'
    return 'video'
