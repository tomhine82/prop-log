"""Unit tests for tools/withings_auth.py + tools/withings_sync.py against a local mock of Withings + Supabase.
Run:  python3 tests/test_withings_tools.py      (uses fake credentials only – never the real secrets)"""
import base64, datetime as dt, http.server, json, os, shutil, stat, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from zoneinfo import ZoneInfo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); TOOLS = os.path.join(ROOT, 'tools')
LON = ZoneInfo('Europe/London'); results = []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:600]))
def ts(s): return int(dt.datetime.fromisoformat(s).replace(tzinfo=LON).timestamp())
def iso(sec): return dt.datetime.fromtimestamp(sec, dt.timezone.utc).isoformat().replace('+00:00', 'Z')
def jwt(role): b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip('='); return b({'alg': 'HS256'}) + '.' + b({'role': role}) + '.sig'
SECRET = 'sb_secret_TESTKEY_abcdefgh'; LEGACY = jwt('service_role')

class Mock:
    def __init__(s): s.reset()
    def reset(s):
        s.codes = {'GOODCODE'}; s.refresh = {}; s.access = {}; s.n = 0; s.groups = []; s.rows = {}; s.calls = []
        s.users = [{'id': 'aaaaaaaa-0000-4000-8000-000000000001', 'email': 'someone@else.com'},
                   {'id': 'bbbbbbbb-0000-4000-8000-0000000000aa', 'email': 'TomHine82@btinternet.com'}]
        s.key = SECRET; s.seq = 0; s.fail_refresh = False; s.admin_fails = False
    def issue(s, expires_in=10800):
        s.n += 1; at, rt = f'AT{s.n}', f'RT{s.n}'; s.access[at] = time.time() + expires_in; s.refresh[rt] = True
        return {'status': 0, 'body': {'userid': 4242, 'access_token': at, 'refresh_token': rt, 'expires_in': expires_in, 'scope': 'user.metrics', 'token_type': 'Bearer'}}
M = Mock()

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, st, obj):
        b = json.dumps(obj).encode() if obj is not None else b''
        self.send_response(st); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n = int(self.headers.get('Content-Length') or 0); return self.rfile.read(n).decode() if n else ''
    def do_GET(self): self.route('GET')
    def do_POST(self): self.route('POST')
    def route(self, m):
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query); raw = self.body()
        M.calls.append((m, u.path, {k.lower(): v for k, v in self.headers.items()}, q, raw))
        if u.path == '/v2/oauth2':
            f = dict(urllib.parse.parse_qsl(raw))
            if f.get('client_id') != 'test-client' or f.get('client_secret') != 'test-secret': return self.send(200, {'status': 503, 'error': 'invalid client'})
            if f.get('grant_type') == 'authorization_code':
                if f.get('code') in M.codes and f.get('redirect_uri') == 'https://tomhine82.github.io/prop-log/withings.html':
                    M.codes.discard(f['code']); return self.send(200, M.issue())
                return self.send(200, {'status': 503, 'error': 'Invalid code'})
            if f.get('grant_type') == 'refresh_token':
                if M.fail_refresh or not M.refresh.pop(f.get('refresh_token'), None): return self.send(200, {'status': 503, 'error': 'invalid refresh_token'})
                return self.send(200, M.issue())
            return self.send(200, {'status': 503})
        if u.path == '/measure':
            f = dict(urllib.parse.parse_qsl(raw)); at = (self.headers.get('Authorization') or '')[7:]
            if M.access.get(at, 0) < time.time(): return self.send(200, {'status': 401, 'error': 'invalid_token'})
            assert f['action'] == 'getmeas' and f['meastypes'] == '1,6,8,76,77,88' and f['category'] == '1'
            g = M.groups
            if 'lastupdate' in f: g = [x for x in g if x['modified'] > int(f['lastupdate'])]
            if 'startdate' in f: g = [x for x in g if int(f['startdate']) <= x['date'] <= int(f['enddate'])]
            off = int(f.get('offset') or 0); page = g[off:off + 3]   # tiny pages to exercise 'more'/'offset'
            more = off + 3 < len(g)
            return self.send(200, {'status': 0, 'body': {'updatetime': 1800000000, 'timezone': 'Europe/London', 'measuregrps': page, 'more': 1 if more else 0, 'offset': off + 3 if more else 0}})
        # ---- Supabase ----
        if self.headers.get('apikey') != M.key: return self.send(401, {'message': 'Invalid API key'})
        auth = self.headers.get('Authorization')
        if M.key.startswith('sb_') and auth: return self.send(401, {'message': 'Invalid JWT'})
        if M.key.startswith('eyJ') and auth != 'Bearer ' + M.key: return self.send(401, {'message': 'bad auth'})
        if u.path == '/auth/v1/admin/users':
            if M.admin_fails: return self.send(403, {'msg': 'not allowed'})
            return self.send(200, {'users': M.users, 'aud': 'authenticated'})
        if u.path == '/rest/v1/proplog_data':
            if m == 'GET':
                g1 = lambda k: q[k][0].split('.', 1)[1] if k in q else None
                if q.get('select') == ['user_id']:
                    return self.send(200, [{'user_id': k[0]} for k in M.rows if k[1] == g1('profile')])
                ids = [v for v in q.get('id', [])]; lo = [x[4:] for x in ids if x.startswith('gte.')]; hi = [x[4:] for x in ids if x.startswith('lte.')]
                out = [dict(id=k[3], data=r['data'], updated_at=r['updated_at'], deleted=r['deleted']) for k, r in sorted(M.rows.items())
                       if k[0] == g1('user_id') and k[1] == g1('profile') and k[2] == g1('kind') and (not lo or k[3] >= lo[0]) and (not hi or k[3] <= hi[0])]
                return self.send(200, out)
            if m == 'POST':
                assert q.get('on_conflict') == ['user_id,profile,kind,id']
                for r in json.loads(raw):
                    assert set(r) == {'user_id', 'profile', 'kind', 'id', 'data', 'updated_at', 'deleted'}, r
                    if r['kind'] not in ('session', 'bodyweight'): return self.send(400, {'code': '23514', 'message': 'kind check'})
                    k = (r['user_id'], r['profile'], r['kind'], r['id']); old = M.rows.get(k)
                    p = lambda x: dt.datetime.fromisoformat(x.replace('Z', '+00:00'))
                    if old and p(r['updated_at']) < p(old['updated_at']): continue   # LWW trigger
                    M.seq += 1; M.rows[k] = {**r, 'synced_at': M.seq}
                return self.send(201, None)
        return self.send(404, {'message': 'not mocked ' + u.path})

srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_port}'
HOME = tempfile.mkdtemp(prefix='plw-'); shutil.rmtree(HOME)   # tools must create it (700)
ENV = {k: v for k, v in os.environ.items() if k not in ('WITHINGS_CLIENT_ID', 'WITHINGS_CLIENT_SECRET', 'SUPABASE_SERVICE_KEY', 'SUPABASE_ANON_KEY')}
ENV.update({'WITHINGS_CLIENT_ID': 'test-client', 'WITHINGS_CLIENT_SECRET': 'test-secret', 'WITHINGS_API_BASE': BASE,
            'WITHINGS_ACCOUNT_BASE': BASE, 'SUPABASE_URL': BASE, 'PROPLOG_HOME': HOME, 'PROPLOG_TZ': 'Europe/London'})
def run(script, *args, env=None, timeout=60):
    e = dict(ENV); e.update(env or {})
    p = subprocess.run([sys.executable, os.path.join(TOOLS, script), *args], env=e, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr
TOK = os.path.join(HOME, 'withings_tokens.json'); STATE = os.path.join(HOME, 'withings_state.json')
tok = lambda: json.load(open(TOK))
TOM = 'bbbbbbbb-0000-4000-8000-0000000000aa'

# ================= auth =================
PORT = 18765
proc = subprocess.Popen([sys.executable, os.path.join(TOOLS, 'withings_auth.py'), '--port', str(PORT), '--timeout', '20'],
                        env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
url = None
for line in proc.stdout:
    if line.startswith(BASE + '/oauth2_user/authorize2?'): url = line.strip(); break
qa = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)) if url else {}
ok('auth: prints authorize URL with client id, redirect, scope, random state',
   qa.get('client_id') == 'test-client' and qa.get('redirect_uri') == 'https://tomhine82.github.io/prop-log/withings.html'
   and qa.get('scope') == 'user.metrics' and qa.get('response_type') == 'code' and len(qa.get('state', '')) >= 24, qa)
ok('auth: home dir is 700', stat.S_IMODE(os.stat(HOME).st_mode) == 0o700)
def cb(query):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/callback?' + query, timeout=10) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()
st, body = cb(urllib.parse.urlencode({'code': 'GOODCODE', 'state': 'wrong'}))
ok('auth: wrong state rejected (400), code not exchanged', st == 400 and 'GOODCODE' in M.codes and not os.path.exists(TOK))
st, body = cb(urllib.parse.urlencode({'code': 'GOODCODE', 'state': qa['state']}))
out = proc.communicate(timeout=10)[0]
ok('auth: callback exchanges code, success page, exit 0', st == 200 and 'Withings connected' in body and proc.returncode == 0, (st, body[:200], out))
ok('auth: tokens saved 600 with refresh token', os.path.exists(TOK) and stat.S_IMODE(os.stat(TOK).st_mode) == 0o600 and tok()['refresh_token'] == 'RT1' and tok()['expires_at'] > time.time() + 10000)
ok('auth: no secrets/tokens in output', 'test-secret' not in out and 'AT1' not in out and 'RT1' not in out and 'GOODCODE' not in out, out)
ok('auth: url file removed after success', not os.path.exists(os.path.join(HOME, 'withings_authorize_url.txt')))
code, out = run('withings_auth.py', '--port', str(PORT), '--timeout', '1', '--no-print-url')
ok('auth: timeout exits non-zero with message', code != 0 and 'Timed out' in out, out)
code, out = run('withings_auth.py', '--code', 'BADCODE')
ok('auth: --code with invalid code fails clearly', code == 3 and 'token request failed' in out, out)

# ================= sync data =================
NOW = int(time.time())
def grp(when, kg=None, fat=None, muscle=None, attrib=0, gid=None, mod=None, extra=()):
    t = ts(when) if isinstance(when, str) else when; ms = []
    if kg is not None: ms.append({'value': int(round(kg * 1000)), 'unit': -3, 'type': 1})
    if fat is not None: ms.append({'value': int(round(fat * 100)), 'unit': -2, 'type': 6})
    if muscle is not None: ms.append({'value': int(round(muscle * 100)), 'unit': -2, 'type': 76})
    ms += list(extra)
    return {'grpid': gid or t, 'attrib': attrib, 'date': t, 'created': t, 'modified': mod or t, 'category': 1, 'deviceid': 'x', 'measures': ms}
day = lambda n: (dt.datetime.now(LON) - dt.timedelta(days=n)).date().isoformat()
D1, D2, D3, D4, D5, D6 = day(10), day(9), day(8), day(7), day(6), day(400)
M.groups = sorted([
    grp(D1 + 'T07:00:00', 135.2, 28.1, 60.1, extra=[{'value': 4512, 'unit': -2, 'type': 8}, {'value': 4400, 'unit': -2, 'type': 77}, {'value': 520, 'unit': -2, 'type': 88}]),
    grp(D1 + 'T21:30:00', 136.0, 28.4, 60.3),                      # later same day wins
    grp(D1 + 'T23:30:00', 70.0, attrib=1),                         # ambiguous user: ignored
    grp(D2 + 'T07:10:00', 134.9, 27.9, 60.0),                      # manual app entry newer -> skip
    grp(D3 + 'T07:05:00', 134.7),                                  # tombstone newer -> skip
    grp(D4 + 'T06:55:00', 134.6, 27.5, 60.2),                      # older manual entry -> update
    grp(D5 + 'T06:50:00', fat=27.0),                               # no weight -> skipped
    grp(D6 + 'T07:00:00', 140.0),                                  # >365 days old: outside first window
], key=lambda g: g['date'])
OLD = lambda d, h: iso(ts(d + 'T' + h))
M.rows[(TOM, 'tom', 'bodyweight', D2)] = {'user_id': TOM, 'profile': 'tom', 'kind': 'bodyweight', 'id': D2, 'data': {'id': 'm2', 'date': D2, 'kg': 135.5, 'updatedAt': 0}, 'updated_at': OLD(D2, '09:00:00'), 'deleted': False, 'synced_at': 0}
M.rows[(TOM, 'tom', 'bodyweight', D3)] = {'user_id': TOM, 'profile': 'tom', 'kind': 'bodyweight', 'id': D3, 'data': {}, 'updated_at': OLD(D3, '12:00:00'), 'deleted': True, 'synced_at': 0}
M.rows[(TOM, 'tom', 'bodyweight', D4)] = {'user_id': TOM, 'profile': 'tom', 'kind': 'bodyweight', 'id': D4, 'data': {'id': 'm4', 'date': D4, 'kg': 135.0, 'updatedAt': 0}, 'updated_at': OLD(D4, '06:00:00'), 'deleted': False, 'synced_at': 0}
M.rows[(TOM, 'nikki', 'bodyweight', D1)] = {'user_id': TOM, 'profile': 'nikki', 'kind': 'bodyweight', 'id': D1, 'data': {'id': 'n', 'date': D1, 'kg': 68.0, 'updatedAt': 0}, 'updated_at': OLD(D1, '06:00:00'), 'deleted': False, 'synced_at': 0}
before = json.dumps(sorted((list(k), v) for k, v in M.rows.items()), sort_keys=True, default=str)

# expire the access token so the first call must refresh
t = tok(); t['expires_at'] = NOW - 10; json.dump(t, open(TOK, 'w'))
code, out = run('withings_sync.py')
ok('sync: no service key -> clear error, exit 2', code == 2 and 'SUPABASE_SERVICE_KEY is not set' in out, out)
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': jwt('anon')})
ok('sync: anon key refused', code == 2 and 'does not look like a secret' in out, out)

code, out = run('withings_sync.py', '--dry-run')
ok('sync: dry-run works without service key', code == 0 and 'Dry run' in out and '4 day(s) with a weight' in out, out)
ok('sync: refresh rotated + persisted atomically (600)', tok()['refresh_token'] == 'RT2' and stat.S_IMODE(os.stat(TOK).st_mode) == 0o600, tok().get('refresh_token'))
code, out = run('withings_sync.py', '--dry-run', env={'SUPABASE_SERVICE_KEY': SECRET})
ok('sync: dry-run with key shows plan, writes nothing, no state', code == 0 and 'Plan: 2 insert' not in out and 'insert, 1 update' in out and json.dumps(sorted((list(k), v) for k, v in M.rows.items()), sort_keys=True, default=str) == before and not os.path.exists(STATE), out)
ok('sync: output has no secrets', all(s not in out for s in (SECRET, 'test-secret', 'AT2', 'RT2')), out)
posts_before = sum(1 for c in M.calls if c[0] == 'POST' and c[1] == '/rest/v1/proplog_data')
ok('sync: dry-run made no Supabase POST', posts_before == 0)

code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': SECRET})
R = lambda d, p='tom': M.rows.get((TOM, p, 'bodyweight', d))
ok('sync: real run exit 0', code == 0 and 'OK: wrote 2 row(s)' in out, out)
r1 = R(D1)
ok('sync: D1 inserted, latest of day wins, extra fields + source', r1 and r1['data']['kg'] == 136.0 and r1['data']['fat_pct'] == 28.4 and r1['data']['muscle_kg'] == 60.3
   and r1['data']['fat_kg'] == 45.12 and r1['data']['hydration_kg'] == 44.0 and r1['data']['bone_kg'] == 5.2 and r1['data']['source'] == 'withings'
   and r1['data']['date'] == D1 and r1['id'] == D1 and r1['user_id'] == TOM and r1['profile'] == 'tom', r1)
ok('sync: updated_at == data.updatedAt == latest measurement time', r1 and r1['updated_at'] == iso(ts(D1 + 'T21:30:00')).replace('Z', '.000Z') and r1['data']['updatedAt'] == ts(D1 + 'T21:30:00') * 1000, r1 and r1['updated_at'])
ok('sync: newer manual app entry kept', R(D2)['data']['kg'] == 135.5 and 'source' not in R(D2)['data'])
ok('sync: app tombstone respected', R(D3)['deleted'] is True)
ok('sync: older manual entry updated, app id kept', R(D4)['data']['kg'] == 134.6 and R(D4)['data']['id'] == 'm4' and R(D4)['data']['source'] == 'withings')
ok('sync: composition-only day and >365d day skipped', R(D5) is None and R(D6) is None)
ok('sync: nikki untouched', R(D1, 'nikki')['data']['kg'] == 68.0)
s = json.load(open(STATE))
ok('sync: state saved (cursor + cached user id, 600)', s['lastupdate'] == 1800000000 and s['user_id'] == TOM and stat.S_IMODE(os.stat(STATE).st_mode) == 0o600, s)
sb = [c for c in M.calls if c[1].startswith('/rest/') or c[1].startswith('/auth/')]
ok('sync: sb_secret key sent on apikey only', all(c[2].get('apikey') == SECRET and 'authorization' not in c[2] for c in sb))
ok('sync: admin lookup matched email case-insensitively', any(c[1] == '/auth/v1/admin/users' for c in sb))

# ---- incremental: a new evening weigh-in on D1 + a new day; cursor semantics ----
M.calls.clear()
M.groups.append(grp(D1 + 'T22:45:00', 135.8, mod=1800000100))           # newer same-day weigh-in (weight only)
nd = day(1); M.groups.append(grp(nd + 'T07:00:00', 134.0, 27.0, 60.5, mod=1800000200))
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': SECRET})
meas = [dict(urllib.parse.parse_qsl(c[4])) for c in M.calls if c[1] == '/measure']
ok('sync: incremental uses lastupdate then re-reads affected days', code == 0 and meas[0].get('lastupdate') == '1800000000' and 'startdate' in meas[-1], (out, meas))
ok('sync: incremental did not call admin API (cached user id)', not any(c[1] == '/auth/v1/admin/users' for c in M.calls))
r1 = R(D1)['data']
ok('sync: D1 updated: weight from 22:45, fat/muscle from the latest group having them', r1['kg'] == 135.8 and r1['fat_pct'] == 28.4 and r1['muscle_kg'] == 60.3, r1)
ok('sync: new day inserted', R(nd) and R(nd)['data']['kg'] == 134.0)
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': SECRET})
ok('sync: nothing new -> 0 writes', code == 0 and 'OK: wrote 0 row(s)' in out, out)
code, out = run('withings_sync.py', '--full', env={'SUPABASE_SERVICE_KEY': SECRET})
ok('sync: --full re-run is idempotent (all unchanged/skipped)', code == 0 and 'OK: wrote 0 row(s)' in out and 'unchanged' in out, out)

# ---- legacy service_role JWT: both headers ----
M.key = LEGACY; M.calls.clear(); os.remove(STATE)
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': LEGACY})
sb = [c for c in M.calls if c[1].startswith('/rest/') or c[1].startswith('/auth/')]
ok('sync: legacy JWT -> apikey + Authorization Bearer', code == 0 and sb and all(c[2].get('authorization') == 'Bearer ' + LEGACY for c in sb), out)

# ---- admin API unavailable -> user_id from existing rows ----
M.admin_fails = True; os.remove(STATE)
code, out = run('withings_sync.py', '--dry-run', env={'SUPABASE_SERVICE_KEY': LEGACY})
ok('sync: falls back to user_id from existing rows', code == 0 and 'Supabase user: bbbbbbbb' in out, out)
M.admin_fails = False

# ---- refresh token dead -> exit 3, re-auth message ----
t = tok(); t['expires_at'] = 0; json.dump(t, open(TOK, 'w')); M.fail_refresh = True
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': LEGACY})
ok('sync: expired refresh token -> exit 3 + re-auth hint', code == 3 and 're-auth needed' in out and 'withings_auth.py' in out, out)
M.fail_refresh = False
os.remove(TOK)
code, out = run('withings_sync.py', '--dry-run')
ok('sync: missing tokens -> exit 3', code == 3 and 'withings_auth.py' in out, out)

# ---- Supabase permission error -> exit 4 + migration hint ----
M.issue(); json.dump({'access_token': f'AT{M.n}', 'refresh_token': f'RT{M.n}', 'expires_at': NOW + 9999, 'userid': '4242'}, open(TOK, 'w'))
orig = H.route
def deny(self, m):
    if self.path.startswith('/rest/v1/proplog_data') and m == 'POST':
        self.body(); return self.send(403, {'code': '42501', 'message': 'permission denied for table proplog_data'})
    return orig(self, m)
H.route = deny; M.groups.append(grp(day(0) + 'T06:00:00', 133.9, mod=1900000000))
code, out = run('withings_sync.py', env={'SUPABASE_SERVICE_KEY': LEGACY})
ok('sync: permission denied -> exit 4 + points at supabase/withings.sql', code == 4 and 'withings.sql' in out, out)
H.route = orig

srv.shutdown(); shutil.rmtree(HOME, ignore_errors=True)
print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
sys.exit(0 if all(r for _, r in results) else 1)
