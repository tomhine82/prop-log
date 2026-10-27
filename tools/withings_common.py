"""Shared helpers for the Prop Log Withings tools (no secrets in here).

Secrets come only from the environment: WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, SUPABASE_SERVICE_KEY.
Token/state files live in $PROPLOG_HOME (default /home/box/.proplog, dir 700, files 600).
Endpoints can be overridden for tests with WITHINGS_API_BASE / WITHINGS_ACCOUNT_BASE / SUPABASE_URL.
"""
import json, os, tempfile, time, urllib.error, urllib.parse, urllib.request

HOME = os.environ.get('PROPLOG_HOME', '/home/box/.proplog')
TOKENS = os.path.join(HOME, 'withings_tokens.json')
STATE = os.path.join(HOME, 'withings_state.json')
API = os.environ.get('WITHINGS_API_BASE', 'https://wbsapi.withings.net').rstrip('/')
ACCOUNT = os.environ.get('WITHINGS_ACCOUNT_BASE', 'https://account.withings.com').rstrip('/')
REDIRECT_URI = os.environ.get('WITHINGS_REDIRECT_URI', 'https://tomhine82.github.io/prop-log/withings.html')
UA = 'prop-log-withings/1.0'


class Fail(Exception):
    """Fatal error with a user-facing message and exit code."""
    def __init__(self, msg, code=1):
        super().__init__(msg); self.code = code


def env(name, required=True):
    v = os.environ.get(name, '').strip()
    if required and not v:
        raise Fail(f'{name} is not set in the environment', 2)
    return v


def ensure_home():
    os.makedirs(HOME, mode=0o700, exist_ok=True)
    os.chmod(HOME, 0o700)


def write_json_atomic(path, obj):
    """Write JSON via temp file + fsync + rename so a crash never leaves a half-written token file."""
    ensure_home()
    fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', dir=os.path.dirname(path))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f, indent=2, sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def http(method, url, data=None, headers=None, json_body=None, timeout=30):
    """Return (status, parsed_json_or_text). Never raises for HTTP status codes."""
    h = {'User-Agent': UA, 'Accept': 'application/json'}
    h.update(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode(); h['Content-Type'] = 'application/json'
    elif data is not None:
        body = urllib.parse.urlencode(data).encode(); h['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Fail(f'Network error calling {urllib.parse.urlsplit(url).netloc}: {getattr(e, "reason", e)}', 1)
    txt = raw.decode('utf-8', 'replace')
    try:
        return status, (json.loads(txt) if txt else None)
    except ValueError:
        return status, txt


def withings_token_request(params):
    """POST /v2/oauth2 action=requesttoken. Returns the token dict to persist. Raises Fail on error."""
    p = {'action': 'requesttoken', 'client_id': env('WITHINGS_CLIENT_ID'),
         'client_secret': env('WITHINGS_CLIENT_SECRET'), **params}
    status, j = http('POST', API + '/v2/oauth2', data=p)
    if status != 200 or not isinstance(j, dict) or j.get('status') != 0 or not isinstance(j.get('body'), dict):
        st = j.get('status') if isinstance(j, dict) else None
        err = (j.get('error') if isinstance(j, dict) else None) or f'HTTP {status}'
        raise Fail(f'Withings token request failed (status {st}: {err})', 3)
    b = j['body']
    if not b.get('access_token') or not b.get('refresh_token'):
        raise Fail('Withings token response missing tokens', 3)
    now = int(time.time())
    return {'access_token': b['access_token'], 'refresh_token': b['refresh_token'],
            'expires_at': now + int(b.get('expires_in') or 10800), 'obtained_at': now,
            'userid': str(b.get('userid', '')), 'scope': b.get('scope', ''), 'token_type': b.get('token_type', 'Bearer')}
