"""v14: visible 'not synced' / 'not backed up' status, save-time warning, retry of leftover
sessions (including another signed-in profile) when the app opens.
Needs the site at http://localhost:8766/prop-log/. Supabase is mocked."""
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

html, sw = read('index.html'), read('sw.js')
ok('sw cache proplog-v14', "const CACHE = 'proplog-v14';" in sw)
ok('sessions and plans pushed separately', "const plans=push.filter(r=>r.kind==='plan'), others=push.filter(r=>r.kind!=='plan');" in html)
ok('syncAll retries every signed-in profile', 'function syncAll' in html and 'syncAll()' in html)
ok('banner markup present', 'id="syncBanner"' in html and 'id="syncBannerBtn"' in html)
ok('save warns when signed out', 'on this phone only' in html and 'not backed up' in html)

NOW = int(time.time() * 1000)
SESS = {'id': 'loc1', 'date': '2026-11-03', 'type': 'Other', 'exercises': [{'name': 'Squat', 'sets': [{'reps': 5, 'weight': 40}]}],
        'feel': None, 'rpe': None, 'notes': '', 'createdAt': NOW, 'updatedAt': NOW}
NIKKI = {'id': 'nik1', 'date': '2026-11-04', 'type': 'Other', 'exercises': [{'name': 'Glute bridge', 'sets': [{'reps': 12, 'weight': 10}]}],
         'feel': None, 'rpe': None, 'notes': '', 'createdAt': NOW, 'updatedAt': NOW}

def tok(uid, email, prefix):
    return {'access_token': prefix, 'refresh_token': 'r-'+prefix, 'expires_at': int(time.time()) + 3600,
            'expires_in': 3600, 'token_type': 'bearer', 'user': {'id': uid, 'email': email}}

with sync_playwright() as p:
    b = p.chromium.launch()
    M = {'posts': [], 'mode': 'ok'}
    def handler(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/auth/v1/token' in r.url:
            body = json.loads(r.post_data or '{}')
            if body.get('grant_type') == 'password' or body.get('email'):
                return route.fulfill(status=200, headers=cors, content_type='application/json',
                    body=json.dumps(tok('u-tom', body.get('email') or 'tom@example.com', 'att')))
            return route.fulfill(status=200, headers=cors, content_type='application/json',
                body=json.dumps(tok('u-keep', 'keep@example.com', 'atr')))
        if '/rest/v1/proplog_data' in r.url:
            if r.method == 'GET':
                return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
            rows = json.loads(r.post_data or '[]')
            M['posts'].append(rows)
            if M['mode'] == 'fail':
                return route.fulfill(status=500, headers=cors, content_type='application/json',
                    body='{"msg":"server exploded"}')
            return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')

    def open_page(tag, extra_js='', route=True):
        ctx = b.new_context(viewport={'width': 390, 'height': 844}, locale='en-GB', timezone_id='Europe/London', service_workers='block')
        if route: ctx.route(SB + '/**', handler)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('dialog', lambda d: d.accept())
        pg.goto(URL)
        pg.evaluate("localStorage.clear()")
        js = "localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','tom');"
        pg.evaluate(js + extra_js)
        pg.reload()
        pg.wait_for_function('window.__proplog&&window.__proplog.sync', timeout=8000)
        return ctx, pg

    # ---- signed out with a local session: banner + pill ----
    extra = "localStorage.setItem('proplog.v1:tom',%s);" % json.dumps(json.dumps({'version': 1, 'sessions': [SESS], 'bodyweight': []}))
    ctx, pg = open_page('signedout', extra)
    pg.wait_for_timeout(400)
    ban = pg.inner_text('#syncBanner')
    pill = pg.inner_text('#syncPill')
    hidden = pg.evaluate("document.getElementById('syncBanner').classList.contains('hidden')")
    ok('signed out + local session: banner visible', (not hidden) and '1 session is on this phone' in ban and 'not backed up' in ban, ban)
    ok('signed out: pill says not backed up', 'not backed up' in pill and 'hidden' not in (pg.get_attribute('#syncPill', 'class') or ''), pill)
    pg.click('#syncPill')
    pg.wait_for_timeout(300)
    ok('signed-out pill opens the sign-in screen', pg.evaluate("document.getElementById('view-data').classList.contains('active')") and pg.is_visible('#syncEmail'), pg.evaluate("document.getElementById('view-data').className"))
    ctx.close()

    # ---- saving while signed out ----
    ctx, pg = open_page('saveout')
    pg.wait_for_timeout(300)
    pg.select_option('#exPick', label='Back squat')
    pg.click('#addEx')
    pg.wait_for_selector('.ex input[data-f=reps]')
    pg.fill('.ex input[data-f=reps]', '5')
    pg.fill('.ex input[data-f=weight]', '40')
    pg.click('#saveSession')
    pg.wait_for_timeout(600)
    toast = pg.inner_text('#toast')
    ban = pg.inner_text('#syncBanner')
    ok('save while signed out warns it is not backed up', 'on this phone only' in toast and 'not backed up' in toast, toast)
    ok('save while signed out shows the banner with the new session', '1 session is on this phone' in ban and 'not backed up' in ban, ban)
    ctx.close()

    # ---- signed in, upload fails: error on banner ----
    M['mode'] = 'fail'; M['posts'] = []
    signed = {'session': {'access_token': 'at0', 'refresh_token': 'rt0', 'expires_at': int(time.time()) + 3600,
                          'user': {'id': 'u-tom', 'email': 'tom@example.com'}}, 'linkedUser': 'u-tom',
              'queue': ['session:loc1'], 'known': {'session:loc1': NOW}, 'cursor': '2026-11-01T00:00:00+00:00'}
    extra = ("localStorage.setItem('proplog.v1:tom',%s);"
             "localStorage.setItem('proplog.sync:tom',%s);") % (
        json.dumps(json.dumps({'version': 1, 'sessions': [SESS], 'bodyweight': []})),
        json.dumps(json.dumps(signed)))
    ctx, pg = open_page('failup', extra)
    pg.wait_for_function("document.getElementById('syncBanner') && !document.getElementById('syncBanner').classList.contains('hidden')", timeout=8000)
    txt = pg.inner_text('#syncBanner') + ' ' + pg.inner_text('#syncStatus')
    ok('failed upload shows not-synced banner with the error', 'Not synced' in txt and 'server exploded' in txt, txt)
    ok('failed upload kept the session queued', 'session:loc1' in pg.evaluate("window.__proplog.sync.state('tom').queue"), pg.evaluate("window.__proplog.sync.state('tom')"))
    ctx.close()

    # ---- another profile's queued session uploads when the app opens on Tom ----
    M['mode'] = 'ok'; M['posts'] = []
    nikki_sync = {'session': {'access_token': 'atn', 'refresh_token': 'rtn', 'expires_at': int(time.time()) + 3600,
                              'user': {'id': 'u-nikki', 'email': 'nikki@example.com'}}, 'linkedUser': 'u-nikki',
                  'queue': ['session:nik1'], 'known': {'session:nik1': NOW}, 'cursor': '2026-11-01T00:00:00+00:00'}
    extra = ("localStorage.setItem('proplog.v1:nikki',%s);"
             "localStorage.setItem('proplog.sync:nikki',%s);") % (
        json.dumps(json.dumps({'version': 1, 'sessions': [NIKKI], 'bodyweight': []})),
        json.dumps(json.dumps(nikki_sync)))
    ctx, pg = open_page('retryother', extra)
    end = time.time() + 8
    while time.time() < end and not any(any(r.get('profile') == 'nikki' and r.get('id') == 'nik1' for r in chunk) for chunk in M['posts']):
        pg.wait_for_timeout(150)
    flat = [r for chunk in M['posts'] for r in chunk]
    ok('queued session on another profile uploads on start', any(r.get('profile') == 'nikki' and r.get('kind') == 'session' and r.get('id') == 'nik1' for r in flat), flat)
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
