"""Unit tests for tools/set_password.py against a local mock of the Supabase auth admin API (fake keys only)."""
import base64, http.server, json, os, subprocess, sys, threading, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); TOOL = os.path.join(ROOT, 'tools', 'set_password.py')
results = []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:500]))
def jwt(role): b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip('='); return b({'alg': 'HS256'}) + '.' + b({'role': role}) + '.sig'
SECRET = 'sb_secret_FAKE_123'; LEGACY = jwt('service_role')
S = {'key': SECRET, 'users': [{'id': f'0000{i:04d}-aaaa-4000-8000-000000000000', 'email': f'user{i}@x.com'} for i in range(250)]
     + [{'id': 'b0b0b0b0-1111-4000-8000-000000000001', 'email': 'TomHine82@btinternet.com', 'email_confirmed_at': None}], 'calls': []}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, st, o):
        b = json.dumps(o).encode(); self.send_response(st); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def handle_any(self, m):
        n = int(self.headers.get('Content-Length') or 0); body = json.loads(self.rfile.read(n)) if n else None
        u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
        S['calls'].append((m, u.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.headers.get('apikey') != S['key']: return self.send(401, {'message': 'Invalid API key'})
        a = self.headers.get('Authorization')
        if S['key'].startswith('sb_') and a: return self.send(401, {'message': 'Invalid JWT'})
        if S['key'].startswith('eyJ') and a != 'Bearer ' + S['key']: return self.send(401, {'message': 'bad'})
        if u.path == '/auth/v1/admin/users' and m == 'GET':
            p, pp = int(q['page'][0]), int(q['per_page'][0]); return self.send(200, {'users': S['users'][(p - 1) * pp:p * pp], 'aud': 'authenticated'})
        if u.path == '/auth/v1/admin/users' and m == 'POST':
            if any(x['email'].lower() == body['email'] for x in S['users']): return self.send(422, {'code': 422, 'error_code': 'email_exists', 'msg': 'exists'})
            nu = {'id': 'c4c4c4c4-2222-4000-8000-000000000002', 'email': body['email'], 'password': body['password'], 'email_confirm': body['email_confirm']}
            S['users'].append(nu); return self.send(200, {k: v for k, v in nu.items() if k != 'password'})
        if u.path.startswith('/auth/v1/admin/users/') and m == 'PUT':
            uid = u.path.rsplit('/', 1)[1]; x = [x for x in S['users'] if x['id'] == uid]
            if not x: return self.send(404, {'msg': 'User not found'})
            if len(body.get('password', '')) < 6: return self.send(422, {'error_code': 'weak_password', 'msg': 'weak'})
            x[0].update(password=body['password'], email_confirm=body.get('email_confirm')); return self.send(200, {'id': uid, 'email': x[0]['email']})
        return self.send(404, {'msg': 'nope'})
    def do_GET(self): self.handle_any('GET')
    def do_POST(self): self.handle_any('POST')
    def do_PUT(self): self.handle_any('PUT')
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
ENV = {k: v for k, v in os.environ.items() if k not in ('SUPABASE_SERVICE_KEY', 'NEW_PASSWORD', 'WITHINGS_CLIENT_ID', 'WITHINGS_CLIENT_SECRET', 'SUPABASE_ANON_KEY')}
ENV['SUPABASE_URL'] = f'http://127.0.0.1:{srv.server_port}'
def run(*args, **env):
    e = dict(ENV); e.update(env); p = subprocess.run([sys.executable, TOOL, *args], env=e, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr
PW = 'Sup3r-Secret-Pass!'
code, out, err = run('--email', 'tomhine82@btinternet.com', SUPABASE_SERVICE_KEY=SECRET, NEW_PASSWORD=PW)
tom = [x for x in S['users'] if x['email'].lower() == 'tomhine82@btinternet.com'][0]
ok('existing user (page 2, case-insensitive) -> updated + id prefix only', code == 0 and out.strip() == 'updated b0b0b0b0' and err == '', (code, out, err))
ok('password set + email_confirm true via PUT', tom.get('password') == PW and tom.get('email_confirm') is True)
ok('sb_secret key on apikey only', all(c[2].get('apikey') == SECRET and 'authorization' not in c[2] for c in S['calls']))
ok('paginated admin lookup', [c for c in S['calls'] if c[0] == 'GET'][-1][1] == '/auth/v1/admin/users' and sum(1 for c in S['calls'] if c[0] == 'GET') == 2)
ok('password/key never printed', PW not in out + err and SECRET not in out + err)
S['calls'].clear(); S['key'] = LEGACY
code, out, err = run('--email', 'Nikki@Example.com', '--password-env', 'NIKKI_PW', SUPABASE_SERVICE_KEY=LEGACY, NIKKI_PW='Nikki-Runs-5k')
nk = [x for x in S['users'] if x['email'] == 'nikki@example.com']
ok('missing user -> created (lowercased email, confirmed) via --password-env', code == 0 and out.strip() == 'created c4c4c4c4' and nk and nk[0]['password'] == 'Nikki-Runs-5k' and nk[0]['email_confirm'] is True, (code, out, err))
ok('legacy JWT on apikey + Authorization', all(c[2].get('authorization') == 'Bearer ' + LEGACY for c in S['calls']))
code, out, err = run('--email', 'x@y.com', SUPABASE_SERVICE_KEY=LEGACY)
ok('missing NEW_PASSWORD -> exit 2', code == 2 and 'NEW_PASSWORD is not set' in err and out == '', err)
code, out, err = run('--email', 'x@y.com', SUPABASE_SERVICE_KEY=LEGACY, NEW_PASSWORD='short')
ok('password < 8 -> exit 2, not echoed', code == 2 and 'shorter than 8' in err and 'short' not in out + err.replace('shorter', ''), err)
code, out, err = run('--email', 'x@y.com', SUPABASE_SERVICE_KEY=jwt('anon'), NEW_PASSWORD=PW)
ok('anon key refused', code == 2 and 'does not look like' in err, err)
code, out, err = run('--email', 'x@y.com', NEW_PASSWORD=PW)
ok('no service key -> exit 2', code == 2 and 'SUPABASE_SERVICE_KEY is not set' in err, err)
code, out, err = run('--email', 'x@y.com', SUPABASE_SERVICE_KEY='sb_secret_WRONG', NEW_PASSWORD=PW)
ok('rejected key -> exit 4, key not printed', code == 4 and 'HTTP 401' in err and 'sb_secret_WRONG' not in err, err)
srv.shutdown()
print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
sys.exit(0 if all(r for _, r in results) else 1)
