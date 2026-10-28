"""Neil profile (v8): profile list + picker, ?p=neil link, per-profile storage, Supabase sync scoped to
profile=neil (email + password sign-in), plans/neil.json loading/rotation, and sw.js precaching it.
Static checks run anywhere; the browser part needs the site served at http://localhost:8766/prop-log/
(same as test_withings_app.py). Supabase is fully mocked – no network, no real keys."""
import json, os, re, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:400]))
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()

# ---------- static ----------
html, sw = read('index.html'), read('sw.js')
m = re.search(r'const PROFILES=(\[.*?\]);', html)
ids = re.findall(r"id:'([a-z0-9_-]+)',name:'([^']+)'", m.group(1)) if m else []
ok('PROFILES: tom, nikki, elspeth, neil, mark in that order', ids == [('tom', 'Tom'), ('nikki', 'Nikki'), ('elspeth', 'Elspeth'), ('neil', 'Neil'), ('mark', 'Mark')], ids)
ok('neil id passes the Supabase profile check', re.fullmatch(r'[a-z0-9_-]{1,32}', 'neil') and "profile ~ '^[a-z0-9_-]{1,32}$'" in read('supabase/schema.sql'))
ok('mum alias still points at elspeth', "PROFILE_ALIAS={mum:'elspeth'}" in html)
ok('sw: cache bumped to proplog-v11', "const CACHE = 'proplog-v11';" in sw)
ok('sw: plans/neil.json precached with the others', all(f"'./plans/{p}.json'" in sw for p in ('tom', 'nikki', 'elspeth', 'neil', 'mark')))
ok('no service key / sb_secret_ in frontend', not re.search(r'service_role|sb_secret_|SUPABASE_SERVICE_KEY', html + sw + read('config.js')))
ok('email + password sign-in kept', "/auth/v1/token?grant_type=password" in html and 'id="syncPass"' in html)

plan = json.loads(read('plans/neil.json'))
ok('neil.json: version 1, athlete Neil, ISO updated, not a placeholder', plan.get('version') == 1 and plan.get('athlete') == 'Neil'
   and re.fullmatch(r'\d{4}-\d{2}-\d{2}', plan.get('updated', '')) and not plan.get('placeholder'))
ws = plan.get('weeks', [])
ok('neil.json: two undated weeks, A-B-A then B-A-B on Mon/Wed/Fri', len(ws) == 2 and all('startDate' not in w for w in ws)
   and [(d['day'], d['title']) for d in ws[0]['days']] == [('Mon', 'Day A'), ('Wed', 'Day B'), ('Fri', 'Day A')]
   and [(d['day'], d['title']) for d in ws[1]['days']] == [('Mon', 'Day B'), ('Wed', 'Day A'), ('Fri', 'Day B')], [[d['title'] for d in w['days']] for w in ws])
days = [d for w in ws for d in w['days']]
ok('neil.json: every exercise has int sets, string reps, targetKg null', all(isinstance(e['sets'], int) and isinstance(e['reps'], str) and e['targetKg'] is None for d in days for e in d['exercises']))
A = [e['name'] for e in ws[0]['days'][0]['exercises']]; B = [e['name'] for e in ws[0]['days'][1]['exercises']]
ok('neil.json: Day A exercises', A == ['Goblet squat or leg press', 'Chest press machine or DB bench press', 'Seated cable row', 'DB Romanian deadlift', "Farmer's carry", 'Dead bug'], A)
ok('neil.json: Day B exercises', B == ['Trap bar deadlift', 'Lat pulldown', 'Seated DB shoulder press', 'Split squat or step-ups', 'Cable face pull', 'Side plank'], B)
n = plan.get('notes', '')
ok('neil.json: notes carry schedule, RIR, progression, warm-up, cool-down, extras', all(s in n for s in ('A-B-A', 'B-A-B', '2 reps in reserve', 'smallest', 'static bike', 'stretching', 'Calf raises'.lower())) or
   all(s.lower() in n.lower() for s in ('A-B-A', 'B-A-B', '2 reps in reserve', 'smallest', 'static bike', 'stretching', 'calf raises')), n)
ok('neil.json: valid session types', all(d['type'] in ('Lower strength', 'Upper strength', 'Running conditioning', 'Ride', 'Rugby training', 'Match', 'Other') for d in days))
try:
    changed = subprocess.run(['git', '-C', ROOT, 'diff', '--name-only', 'HEAD', '--', 'plans/tom.json', 'plans/nikki.json', 'plans/elspeth.json'], capture_output=True, text=True).stdout.strip()
    ok('other plans untouched', changed == '', changed)
except FileNotFoundError: pass

# ---------- browser ----------
from playwright.sync_api import sync_playwright
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', read('config.js')).group(1)
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
with sync_playwright() as p:
    b = p.chromium.launch()
    def context(**kw):
        return b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='en-GB', timezone_id='Europe/London', service_workers='block', **kw)
    def page(ctx, tag):
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'[{tag}] console: {m.text}')); pg.on('dialog', lambda d: d.accept()); return pg

    # ?p=neil link + plan
    ctx = context(); pg = page(ctx, 'link')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.goto(BASE + '?p=neil'); pg.wait_for_function("window.__proplog&&window.__proplog.profile==='neil'&&window.__proplog.plan", timeout=8000)
    ok('?p=neil opens Neil and remembers it', pg.evaluate("localStorage.getItem('proplog.profile')") == 'neil' and pg.inner_text('#profName') == 'Neil')
    ok('?p=neil removed from the URL', '?p=' not in pg.url, pg.url)
    ok('picker sheet not forced open', pg.is_hidden('#profileSheet'))
    ok('plan loaded from network for Neil', pg.evaluate('window.__proplog.planSource') == 'network' and pg.evaluate('window.__proplog.plan.athlete') == 'Neil')
    ok('plan cached under proplog.plan:neil only', pg.evaluate("!!localStorage.getItem('proplog.plan:neil')&&!localStorage.getItem('proplog.plan:tom')"))
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    body = pg.inner_text('#planBody')
    ok('Plan tab shows Neil plan title, days and notes', '3-day full-body strength maintenance' in body.lower() and 'Day A' in body and 'Day B' in body and 'reps in reserve' in body, body[:300])
    pg.reload(); pg.wait_for_function("window.__proplog.profile==='neil'", timeout=5000)
    ok('reload stays on Neil', pg.inner_text('#profName') == 'Neil')
    ctx.close()

    # rotation (anchored on the week of `updated`): w/c 26 Oct = Week 1 (A-B-A), 2 Nov = Week 2 (B-A-B), 9 Nov = Week 1
    for when, mon, wed in (('2026-10-30T09:00:00Z', 'Day A', 'Day B'), ('2026-11-06T09:00:00Z', 'Day B', 'Day A'), ('2026-11-13T09:00:00Z', 'Day A', 'Day B')):
        ctx = context(); pg = page(ctx, 'rot'); pg.clock.install(time=when)
        pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','neil')")
        pg.reload(); pg.wait_for_function("window.__proplog.plan", timeout=8000)
        pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
        t = dict(pg.locator('#planBody details.day[data-day]').evaluate_all("ds=>ds.map(d=>[d.dataset.day,d.querySelector('summary .body .t').childNodes[0].textContent.trim()])"))
        ok(f'rotation {when[:10]}: Mon {mon}, Wed {wed}, Fri {mon}', t.get('Mon') == mon and t.get('Wed') == wed and t.get('Fri') == mon and t.get('Tue') == 'Rest', t)
        if when.startswith('2026-10-30'):
            pg.locator('[data-start=Fri]').click(); pg.wait_for_timeout(300)
            d = pg.evaluate("JSON.parse(localStorage.getItem('proplog.draft.v1:neil'))")
            names = [e.get('name') for e in (d or {}).get('exercises', [])]
            ok('Start this session (Fri Day A) pre-fills Neil draft', names[:1] == ['Goblet squat or leg press'] and len(names) == 6, names)
            ok('draft stored only under :neil', pg.evaluate("!localStorage.getItem('proplog.draft.v1:tom')||JSON.parse(localStorage.getItem('proplog.draft.v1:tom')).exercises.length===0"))
        ctx.close()

    # picker + per-profile storage isolation
    ctx = context(); pg = page(ctx, 'picker')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.evaluate("localStorage.setItem('proplog.v1:tom',JSON.stringify({version:1,sessions:[{id:'t1',date:'2026-10-27',type:'Lower strength',exercises:[],updatedAt:1}],bodyweight:[]}))")
    pg.reload(); pg.wait_for_selector('#profileSheet:not(.hidden)')
    btns = pg.locator('#profGrid [data-prof]').evaluate_all("bs=>bs.map(b=>[b.dataset.prof,b.innerText.replace(/\\s+/g,' ').trim()])")
    ok('first run picker lists Tom, Nikki, Elspeth, Neil, Mark', [x[0] for x in btns] == ['tom', 'nikki', 'elspeth', 'neil', 'mark'] and 'Neil' in btns[3][1] and '0 sessions' in btns[3][1], btns)
    cols = pg.evaluate("getComputedStyle(document.getElementById('profGrid')).gridTemplateColumns.split(' ').length")
    ok('picker is 2 columns', cols == 2, cols)
    pg.click('#profGrid [data-prof=neil]'); pg.wait_for_function("window.__proplog.profile==='neil'")
    ok('picking Neil shows an empty log (Tom data not visible)', pg.evaluate('window.__proplog.db.sessions.length') == 0)
    pg.click('#tabs button[data-view=body]'); pg.fill('#bwKg', '80'); pg.click('#bwSave')
    ok('Neil weigh-in saved to proplog.v1:neil only', json.loads(pg.evaluate("localStorage.getItem('proplog.v1:neil')"))['bodyweight'][0]['kg'] == 80
       and json.loads(pg.evaluate("localStorage.getItem('proplog.v1:tom')"))['bodyweight'] == [])
    pg.screenshot(path=os.path.join(ROOT, 'screenshots', 'neil-body.png')) if os.path.isdir(os.path.join(ROOT, 'screenshots')) else None
    ctx.close()

    # cloud sync: email + password sign-in as Neil, rows scoped to profile=neil
    ctx = context(); pushed, gets, auth = [], [], []
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/auth/v1/token' in r.url:
            auth.append((r.url, json.loads(r.post_data or '{}')))
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps({'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600, 'user': {'id': 'u-neil', 'email': 'neil@example.com'}}))
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET':
            gets.append(r.url); return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST':
            pushed.extend(json.loads(r.post_data)); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb); pg = page(ctx, 'sync')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','neil')")
    pg.evaluate("localStorage.setItem('proplog.v1:neil',JSON.stringify({version:1,sessions:[],bodyweight:[{id:'n1',date:'2026-10-27',kg:81,updatedAt:Date.now()}]}))")
    pg.reload(); pg.wait_for_function("window.__proplog.profile==='neil'")
    pg.click('#tabs button[data-view=data]'); pg.fill('#syncEmail', 'neil@example.com'); pg.fill('#syncPass', 'Neil-Test-Pass-1'); pg.click('#syncSignIn')
    pg.wait_for_function("JSON.parse(localStorage.getItem('proplog.sync:neil')||'{}').lastSync", timeout=8000); pg.wait_for_timeout(500)
    ok('sign-in uses email + password grant', auth and 'grant_type=password' in auth[0][0] and auth[0][1].get('email') == 'neil@example.com' and auth[0][1].get('password') == 'Neil-Test-Pass-1', [a[0] for a in auth])
    ok('session stored under proplog.sync:neil only', pg.evaluate("!!JSON.parse(localStorage.getItem('proplog.sync:neil')).session&&!(JSON.parse(localStorage.getItem('proplog.sync:tom')||'{}').session)"))
    ok('pull queries profile=eq.neil only', gets and all('profile=eq.neil' in u for u in gets), gets)
    ok('push rows are profile neil', pushed and all(x['profile'] == 'neil' and x['user_id'] == 'u-neil' for x in pushed) and any(x['kind'] == 'bodyweight' and x['data'].get('id') == 'n1' for x in pushed), pushed)
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
