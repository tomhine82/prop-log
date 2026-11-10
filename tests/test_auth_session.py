"""v12 'stay signed in': session persisted with backups (localStorage proplog.auth:<p> + IndexedDB proplog-auth),
auto refresh before expiry / on focus, one refresh at a time, and sign-out ONLY for a really invalid refresh token
(never for offline, timeouts, 429 or 5xx). Needs the site at http://localhost:8766/prop-log/. Supabase is mocked."""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', read('config.js')).group(1)
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:600]))

html = read('index.html')
ok('no service key in frontend', not re.search(r'service_role|sb_secret_|SUPABASE_SERVICE_KEY', html + read('sw.js') + read('config.js')))
ok('sw cache proplog-v14', "const CACHE = 'proplog-v14';" in read('sw.js'))

USER = {'id': 'u-tom', 'email': 'tom@example.com'}
def sess(exp_in, rt='rt0', at='at0'):
    return {'session': {'access_token': at, 'refresh_token': rt, 'expires_at': int(time.time()) + exp_in, 'user': USER}, 'linkedUser': 'u-tom'}

with sync_playwright() as p:
    b = p.chromium.launch()
    M = {'mode': 'ok', 'n': 0, 'calls': [], 'delay': 0, 'rest401': 0}
    def handler(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/auth/v1/token' in r.url:
            M['calls'].append(json.loads(r.post_data or '{}').get('refresh_token'))
            if M['delay']: time.sleep(M['delay'])
            m = M['mode']
            if m == 'offline': return route.abort('internetdisconnected')
            if m == '500': return route.fulfill(status=500, headers=cors, content_type='application/json', body='{"msg":"upstream"}')
            if m == '503html': return route.fulfill(status=503, headers=cors, content_type='text/html', body='<h1>down</h1>')
            if m == '429': return route.fulfill(status=429, headers=cors, content_type='application/json', body='{"error_code":"over_request_rate_limit","msg":"Request rate limit reached"}')
            if m == 'invalid': return route.fulfill(status=400, headers=cors, content_type='application/json', body='{"code":400,"error_code":"refresh_token_not_found","msg":"Invalid Refresh Token: Refresh Token Not Found"}')
            if m == 'used': return route.fulfill(status=400, headers=cors, content_type='application/json', body='{"code":400,"error_code":"refresh_token_already_used","msg":"Invalid Refresh Token: Already Used"}')
            if m == 'other400': return route.fulfill(status=400, headers=cors, content_type='application/json', body='{"code":400,"error_code":"validation_failed","msg":"Something odd"}')
            M['n'] += 1
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps({
                'access_token': f'at{M["n"]}', 'refresh_token': f'rt{M["n"]}', 'expires_in': 3600, 'expires_at': int(time.time()) + 3600, 'token_type': 'bearer', 'user': USER}))
        if '/rest/v1/proplog_data' in r.url:
            if M['rest401'] and (r.headers.get('authorization') == 'Bearer at0'):
                M['rest401'] -= 1; return route.fulfill(status=401, headers=cors, content_type='application/json', body='{"message":"JWT expired"}')
            if r.method == 'GET': return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
            return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')

    def fresh(mode, s, extra_js=''):
        M.update(mode=mode, calls=[], delay=0, rest401=0)
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='en-GB', timezone_id='Europe/London', service_workers='block')
        ctx.route(SB + '/**', handler)
        pg = ctx.new_page(); tag = mode
        pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('dialog', lambda d: d.accept())
        pg.goto(URL); pg.evaluate('localStorage.clear()')
        pg.evaluate("new Promise(r=>{const q=indexedDB.deleteDatabase('proplog-auth');q.onsuccess=q.onerror=q.onblocked=()=>r()})")
        js = "localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','tom');"
        if s is not None: js += f"localStorage.setItem('proplog.sync:tom',{json.dumps(json.dumps(s))});"
        pg.evaluate(js + extra_js); pg.reload(); pg.wait_for_function('window.__proplog&&window.__proplog.sync')
        return ctx, pg
    st = lambda pg: pg.evaluate("window.__proplog.sync.state('tom')")
    bak_ls = lambda pg: pg.evaluate("JSON.parse(localStorage.getItem('proplog.auth:tom'))")
    bak_idb = lambda pg: pg.evaluate("window.__proplog.sync.idbGet('tom')")
    def settle(pg, n=1, t=6000):
        end = time.time() + t / 1000
        while len(M['calls']) < n and time.time() < end: pg.wait_for_timeout(100)
        pg.wait_for_timeout(500)

    # ---- unit: what counts as "invalid refresh token" ----
    ctx, pg = fresh('ok', None)
    cases = pg.evaluate("""() => { const f = window.__proplog.sync.invalidRefresh, E = (status, body, message) => Object.assign(new Error(message || 'x'), {status, body});
      return [f(E(400, {error_code:'refresh_token_not_found'})), f(E(400, {error_code:'refresh_token_already_used'})), f(E(400, {msg:'Invalid Refresh Token: Already Used'})),
        f(E(403, {error_code:'session_not_found'})), f(E(400, {error:'invalid_grant'})),
        f(new TypeError('Failed to fetch')), f(E(500, {})), f(E(502, {})), f(E(429, {msg:'Invalid refresh token'})), f(E(408, {})), f(E(400, {error_code:'validation_failed'})), f(E(401, {message:'JWT expired'}))]; }""")
    ok('invalidRefresh: only real invalid-token answers count', cases == [True, True, True, True, True, False, False, False, False, False, False, False], cases)
    ctx.close()

    # ---- successful refresh of an expired token: stored + backed up in localStorage and IndexedDB ----
    ctx, pg = fresh('ok', sess(-60)); settle(pg)
    s = st(pg)['session']
    ok('expired token refreshed on start, rotated tokens stored', s and s['refresh_token'] == 'rt1' and s['access_token'] == 'at1' and M['calls'] == ['rt0'], (s, M['calls']))
    pg.wait_for_timeout(300)
    ok('session backed up in localStorage', (bak_ls(pg) or {}).get('session', {}).get('refresh_token') == 'rt1')
    ok('session backed up in IndexedDB', ((bak_idb(pg) or {}).get('session') or {}).get('refresh_token') == 'rt1', bak_idb(pg))
    ok('signed-in status shown', pg.evaluate("window.__proplog.sync.signedIn('tom')"))

    # ---- restore: main copy lost -> from localStorage backup; both lost -> from IndexedDB ----
    pg.evaluate("localStorage.removeItem('proplog.sync:tom')"); pg.reload(); pg.wait_for_function("window.__proplog.sync.signedIn('tom')", timeout=5000)
    ok('restored from localStorage backup', st(pg)['session']['refresh_token'] in ('rt1', 'rt2'))
    pg.evaluate("localStorage.removeItem('proplog.sync:tom');localStorage.removeItem('proplog.auth:tom')"); pg.reload()
    try: pg.wait_for_function("window.__proplog.sync.signedIn('tom')", timeout=5000); restored = True
    except Exception: restored = False
    ok('restored from IndexedDB backup when localStorage was wiped', restored and st(pg)['session']['user']['id'] == 'u-tom' and bak_ls(pg))

    # ---- sign out clears the backups too ----
    pg.wait_for_timeout(500)
    btn = pg.locator('[data-signout], #signOut, button:has-text("Sign out")')
    pg.click('#tabs button[data-view=data]')
    if btn.count():
        btn.first.click(); pg.wait_for_timeout(600)
        ok('sign out clears session + both backups', not st(pg).get('session') and bak_ls(pg) is None and bak_idb(pg) is None, (st(pg), bak_ls(pg), bak_idb(pg)))
        pg.reload(); pg.wait_for_timeout(800)
        ok('...and it stays signed out after reload', not pg.evaluate("window.__proplog.sync.signedIn('tom')"))
    else:
        ok('sign-out button present', False)
    ctx.close()

    # ---- transient failures never sign out ----
    for mode in ('offline', '500', '503html', '429', 'other400'):
        ctx, pg = fresh(mode, sess(-60)); settle(pg)
        s = st(pg)
        ok(f'refresh fails ({mode}) -> still signed in, tokens kept', s.get('session') and s['session']['refresh_token'] == 'rt0' and len(M['calls']) >= 1, (s, M['calls']))
        ok(f'refresh fails ({mode}) -> backup kept', (bak_ls(pg) or {}).get('session', {}).get('refresh_token') == 'rt0')
        if mode == 'offline':
            M['mode'] = 'ok'; pg.evaluate("window.dispatchEvent(new Event('focus'))"); settle(pg, 2)
            ok('back online + focus -> refresh succeeds', (st(pg).get('session') or {}).get('refresh_token') == 'rt%d' % M['n'] and M['n'] >= 1, (st(pg), M))
        ctx.close()

    # ---- real invalid refresh token -> signed out with a clear message, backups cleared ----
    for mode in ('invalid', 'used'):
        ctx, pg = fresh(mode, sess(-60)); settle(pg); pg.wait_for_timeout(300)
        s = st(pg)
        ok(f'{mode} refresh token -> signed out with "sign in again"', not s.get('session') and 'sign in again' in (s.get('error') or ''), s)
        ok(f'{mode} refresh token -> backups cleared (no zombie restore)', bak_ls(pg) is None and bak_idb(pg) is None)
        pg.reload(); pg.wait_for_timeout(800)
        ok(f'{mode}: not restored after reload', not pg.evaluate("window.__proplog.sync.signedIn('tom')"))
        ctx.close()

    # ---- one refresh at a time (refresh tokens are single-use) ----
    ctx, pg = fresh('ok', sess(3600)); pg.wait_for_timeout(800)
    pg.evaluate("(()=>{const s=JSON.parse(localStorage.getItem('proplog.sync:tom'));s.session.expires_at=1;localStorage.setItem('proplog.sync:tom',JSON.stringify(s));})()")
    M.update(calls=[], delay=0.4)
    res = pg.evaluate("Promise.all([1,2,3,4].map(()=>window.__proplog.sync.ensureToken('tom').then(()=>'ok',e=>'err:'+e.message)))")
    ok('concurrent refreshes share one request', res == ['ok'] * 4 and len(M['calls']) == 1, (res, M['calls']))
    M['delay'] = 0

    # ---- proactive refresh on focus / visibility when expiring within 5 min ----
    pg.evaluate("(()=>{const s=JSON.parse(localStorage.getItem('proplog.sync:tom'));s.session.expires_at=Math.floor(Date.now()/1000)+120;localStorage.setItem('proplog.sync:tom',JSON.stringify(s));})()")
    M['calls'] = []; pg.evaluate("window.dispatchEvent(new Event('focus'))"); settle(pg)
    ok('focus refreshes a token expiring within 5 min', len(M['calls']) == 1 and st(pg)['session']['expires_at'] > time.time() + 3000, M['calls'])
    M['calls'] = []; pg.evaluate("window.dispatchEvent(new Event('focus'))"); pg.wait_for_timeout(600)
    ok('focus with a fresh token does not refresh again', M['calls'] == [])
    pg.evaluate("(()=>{const s=JSON.parse(localStorage.getItem('proplog.sync:tom'));s.session.expires_at=Math.floor(Date.now()/1000)+60;localStorage.setItem('proplog.sync:tom',JSON.stringify(s));})()")
    M['calls'] = []; pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))"); settle(pg)
    ok('visibilitychange refreshes too', len(M['calls']) == 1, M['calls'])
    ctx.close()

    # ---- REST 401 (token revoked/expired server-side) -> refresh once and retry, still signed in ----
    ctx, pg = fresh('ok', sess(3600, rt='rtA', at='at0'))
    M['calls'] = []; M['rest401'] = 1
    pg.evaluate("window.__proplog.sync.sync('tom')"); settle(pg)
    s = st(pg)
    ok('REST 401 -> one refresh + retry, still signed in', s.get('session') and M['calls'] == ['rtA'] and s['session']['access_token'] != 'at0', (s, M['calls']))
    ctx.close()

    # ---- v11 device upgrading: existing session gets backed up on first start ----
    ctx, pg = fresh('ok', sess(3600)); pg.wait_for_timeout(800)
    ok('existing v11 session backed up on first v12 start', (bak_ls(pg) or {}).get('session', {}).get('refresh_token') == 'rt0' and ((bak_idb(pg) or {}).get('session') or {}).get('refresh_token') == 'rt0')
    ok('no refresh needed for a valid token', M['calls'] == [])
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
