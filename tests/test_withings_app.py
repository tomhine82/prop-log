"""Playwright tests for the Withings bits of the app: withings.html redirect, body-composition display,
cloud pull keeping the extra fields, and the service worker (proplog-v11, withings.html not cached as the app).
Needs the site served at http://localhost:8766/prop-log/ (same as test_app_v2.py / test_sync.py)."""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); SHOTS = os.path.join(ROOT, 'screenshots') + '/'
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', open(os.path.join(ROOT, 'config.js')).read()).group(1)
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:400]))
NOW = int(time.time() * 1000); D = 86400000
WD = lambda date, kg, fat, mus, upd: {'id': 'wd-' + date, 'date': date, 'kg': kg, 'fat_pct': fat, 'fat_kg': 38.0, 'muscle_kg': mus, 'hydration_kg': 44.1, 'bone_kg': 5.2, 'source': 'withings', 'measured_at': date + 'T07:00:00+00:00', 'updatedAt': upd}
LOCAL = {'version': 1, 'sessions': [], 'bodyweight': [
    {'id': 'm1', 'date': '2026-10-20', 'kg': 135.4, 'updatedAt': NOW - 7 * D},
    WD('2026-10-24', 134.9, 28.2, 60.4, NOW - 3 * D), WD('2026-10-26', 134.6, 27.9, 60.6, NOW - D)]}
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}

with sync_playwright() as p:
    b = p.chromium.launch()
    def context(**kw):
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale='en-GB', timezone_id='Europe/London', **kw)
        return ctx
    def page(ctx, tag):
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('console', lambda m: m.type == 'error' and errors.append(f'[{tag}] console: {m.text}')); pg.on('dialog', lambda d: d.accept()); return pg

    # ---- withings.html ----
    ctx = context(service_workers='block'); caught = []
    ctx.route('http://127.0.0.1:8765/**', lambda r: (caught.append(r.request.url), r.fulfill(status=200, content_type='text/html', body='<h1>helper</h1>')))
    pg = page(ctx, 'callback')
    pg.goto(BASE + 'withings.html?code=abc123XYZ&state=st-1_2'); pg.wait_for_url('http://127.0.0.1:8765/**')
    ok('withings.html: immediate top-level redirect to local helper with code+state', caught and caught[0] == 'http://127.0.0.1:8765/callback?code=abc123XYZ&state=st-1_2', caught)
    pg.goto(BASE + 'withings.html?code=abc123XYZ&state=st-1_2&noredirect=1')
    ok('withings.html: shows code + note when redirect does not happen', pg.is_visible('#fallback') and pg.inner_text('#code') == 'abc123XYZ' and '127.0.0.1:8765' in pg.inner_text('#fallback')
       and pg.get_attribute('#retry', 'href') == 'http://127.0.0.1:8765/callback?code=abc123XYZ&state=st-1_2')
    pg.screenshot(path=SHOTS + 'withings-callback-fallback.png')
    pg.goto(BASE + 'withings.html?error=access_denied&state=s'); pg.wait_for_url('http://127.0.0.1:8765/**')
    ok('withings.html: error is forwarded to helper too', 'error=access_denied' in caught[-1], caught)
    pg.goto(BASE + 'withings.html')
    ok('withings.html: plain visit shows info, no redirect', pg.is_visible('#idle') and pg.url.startswith(BASE))
    ctx.close()

    # ---- body view with Withings fields ----
    for scheme in ('light', 'dark'):
        ctx = context(service_workers='block', color_scheme=scheme); pg = page(ctx, 'body-' + scheme)
        pg.goto(URL); pg.evaluate('localStorage.clear()')
        pg.evaluate(f"localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','tom');localStorage.setItem('proplog.v1:tom',{json.dumps(json.dumps(LOCAL))})")
        pg.reload(); pg.wait_for_load_state('networkidle')
        pg.click('#tabs button[data-view=body]')
        comp = pg.inner_text('#bwComp') if pg.query_selector('#bwComp') else ''
        ok(f'{scheme}: latest body fat % and muscle shown', '27.9' in comp and '60.6' in comp and 'body fat %' in comp.lower() and 'muscle kg' in comp.lower(), comp)
        ok(f'{scheme}: "from Withings" tags on Withings entries only', pg.locator('#bwBody table .pill.wd').count() == 2 and pg.locator('#bwBody table tr').count() == 3)
        rows = pg.inner_text('#bwBody table')
        ok(f'{scheme}: per-entry composition line', 'fat 28.2% · muscle 60.4 kg' in rows and 'fat 27.9% · muscle 60.6 kg' in rows, rows)
        ok(f'{scheme}: latest weight still the headline stat', pg.inner_text('#bwBody .stats .stat .v') == '134.6')
        if scheme == 'light':
            db = pg.evaluate('window.__proplog.db')['bodyweight']; w = [x for x in db if x['date'] == '2026-10-26'][0]
            ok('normalise keeps Withings fields', all(k in w for k in ('fat_pct', 'fat_kg', 'muscle_kg', 'hydration_kg', 'bone_kg', 'source', 'measured_at')), w)
            ok('header shows latest kg', '134.6' in pg.inner_text('#hdrSub'))
        pg.evaluate('window.scrollTo(0,0)'); pg.wait_for_timeout(200); pg.screenshot(path=SHOTS + f'bodyweight-withings-{scheme}.png', full_page=True)
        if scheme == 'light':
            # manual edit of a Withings day -> no longer tagged as Withings
            pg.fill('#bwDate', '2026-10-26'); pg.fill('#bwKg', '135.0'); pg.click('#bwSave')
            w = [x for x in pg.evaluate('window.__proplog.db')['bodyweight'] if x['date'] == '2026-10-26'][0]
            ok('manual edit of Withings day: kg changed, source manual, tag gone', w['kg'] == 135.0 and w['source'] == 'manual' and pg.locator('#bwBody table .pill.wd').count() == 1, w)
            pg.fill('#bwDate', '2026-10-27'); pg.fill('#bwKg', '134.0'); pg.click('#bwSave')
            ok('plain manual weigh-in still works', any(x['date'] == '2026-10-27' and x['kg'] == 134.0 and 'source' not in x for x in pg.evaluate('window.__proplog.db')['bodyweight']))
        ctx.close()

    # ---- cloud pull of a row written by tools/withings_sync.py ----
    ctx = context(service_workers='block'); pushed = []
    ROW = {'kind': 'bodyweight', 'id': '2026-10-27', 'data': WD('2026-10-27', 134.2, 27.6, 60.9, NOW - 3600000), 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime((NOW - 3600000) / 1000)), 'deleted': False, 'synced_at': '2026-10-27T08:00:00.000001+00:00'}
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET':
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps([ROW] if 'profile=eq.tom' in r.url else []))
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST':
            pushed.extend(json.loads(r.post_data)); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb); pg = page(ctx, 'pull')
    pg.goto(URL); pg.evaluate('localStorage.clear()')
    sess = {'session': {'access_token': 'at', 'refresh_token': 'rt', 'expires_at': int(time.time()) + 3600, 'user': {'id': 'u-tom', 'email': 'tom@example.com'}}, 'linkedUser': 'u-tom'}
    pg.evaluate(f"localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','tom');localStorage.setItem('proplog.v1:tom',{json.dumps(json.dumps({'version':1,'sessions':[],'bodyweight':[]}))});localStorage.setItem('proplog.sync:tom',{json.dumps(json.dumps(sess))})")
    pg.reload(); pg.wait_for_function("window.__proplog.db.bodyweight.length===1", timeout=8000)
    w = pg.evaluate('window.__proplog.db')['bodyweight'][0]
    ok('cloud pull: Withings row lands with extra fields + source', w['kg'] == 134.2 and w['fat_pct'] == 27.6 and w['muscle_kg'] == 60.9 and w['source'] == 'withings' and w['date'] == '2026-10-27', w)
    pg.click('#tabs button[data-view=body]')
    ok('cloud pull: body view shows it tagged', pg.locator('#bwBody .pill.wd').count() >= 1 and '27.6' in pg.inner_text('#bwBody'))
    pg.wait_for_timeout(1200)
    ok('cloud pull: app does not re-push the unchanged Withings row', not any(x['id'] == '2026-10-27' for x in pushed), pushed)
    ctx.close()

    # ---- service worker ----
    ctx = context(); pg = page(ctx, 'sw')
    pg.goto(URL); pg.wait_for_function("navigator.serviceWorker.controller!==null||new Promise(r=>navigator.serviceWorker.ready.then(()=>r(true)))", timeout=10000)
    pg.reload(); pg.wait_for_function("navigator.serviceWorker.controller!==null", timeout=10000)
    keys = pg.evaluate("caches.keys()")
    ok('sw: cache is proplog-v11', keys == ['proplog-v11'], keys)
    pg.wait_for_function("caches.open('proplog-v11').then(c=>c.match('./withings.html')).then(r=>!!r)", timeout=5000)
    ok('sw: withings.html precached', True)
    pg.goto(BASE + 'withings.html'); pg.wait_for_load_state('networkidle'); pg.wait_for_timeout(500)
    t = pg.evaluate("caches.open('proplog-v11').then(c=>c.match('./index.html')).then(r=>r.text())")
    ok('sw: visiting withings.html does not overwrite the cached app page', 'Prop Log – Workout Tracker' in t and 'Withings connect' not in t)
    ctx.set_offline(True); pg.goto(URL); pg.wait_for_load_state()
    ok('sw: app still opens offline', pg.title().startswith('Prop Log – Workout Tracker'))
    ctx.close(); b.close()
print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
