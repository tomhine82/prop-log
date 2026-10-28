"""Mark profile (v10): profile list + picker, ?p=mark link, per-profile storage, Supabase sync scoped to
profile=mark (email + password sign-in), plans/mark.json loading, and sw.js precaching it.
Static checks run anywhere; the browser part needs the site served at http://localhost:8766/prop-log/
(same as test_neil_profile.py). Supabase is fully mocked – no network, no real keys."""
import json, os, re, subprocess, sys
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
ok('PROFILES ends with mark', ids[-1] == ('mark', 'Mark') and ('neil', 'Neil') in ids, ids)
ok('mark id passes the Supabase profile check', re.fullmatch(r'[a-z0-9_-]{1,32}', 'mark') and "profile ~ '^[a-z0-9_-]{1,32}$'" in read('supabase/schema.sql'))
ok('sw: cache bumped to proplog-v10', "const CACHE = 'proplog-v10';" in sw)
ok('sw: plans/mark.json precached with the others', all(f"'./plans/{p}.json'" in sw for p in ('tom', 'nikki', 'elspeth', 'neil', 'mark')))
ok('picker centres a leftover tile', 'button:last-child:nth-child(odd)' in html and 'justify-self:center' in html)

plan = json.loads(read('plans/mark.json'))
ok('mark.json: version 1, athlete Mark, author, ISO updated, not a placeholder', plan.get('version') == 1 and plan.get('athlete') == 'Mark'
   and plan.get('author') == 'Mark Workout Bot' and plan.get('updated') == '2026-10-28' and not plan.get('placeholder'))
ws = plan.get('weeks', [])
days = ws[0]['days'] if len(ws) == 1 else []
ok('mark.json: one undated week, Mon-Sun', len(ws) == 1 and 'startDate' not in ws[0]
   and [d['day'] for d in days] == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
   and [d['title'] for d in days] == ['Strength A', 'Conditioning', 'Strength B', 'Active recovery', 'Strength C', 'Conditioning', 'Rest'])
ok('mark.json: session types match the app', [d['type'] for d in days] == ['Lower strength', 'Other', 'Lower strength', 'Other', 'Upper strength', 'Other', 'Other'])
ok('mark.json: every exercise has int sets, string reps, targetKg null', days and all(isinstance(e['sets'], int) and isinstance(e['reps'], str) and e['targetKg'] is None for d in days for e in d['exercises']))
by = {d['day']: [e['name'] for e in d['exercises']] for d in days}
ok('mark.json: Mon Strength A', by.get('Mon') == ['Barbell back squat', 'Dumbbell bench press', 'Cable seated row', 'Dumbbell walking lunge', 'Cable face pull', 'Plank'], by.get('Mon'))
ok('mark.json: Tue kettlebell circuit', by.get('Tue') == ['Kettlebell swing', 'Goblet squat', 'Push-up', "Kettlebell farmer's carry"] and days[1]['exercises'][0]['sets'] == 5 and days[1]['exercises'][0]['reps'] == '15', by.get('Tue'))
ok('mark.json: Wed Strength B', by.get('Wed') == ['Barbell deadlift', 'Barbell overhead press', 'Cable lat pulldown', 'Dumbbell Romanian deadlift', 'Cable tricep pushdown', 'Cable woodchop'] and days[2]['exercises'][0]['reps'] == '5', by.get('Wed'))
ok('mark.json: Thu recovery, Fri bench, Sat EMOM, Sun light walk', by.get('Thu') == ['Brisk walk', 'Mobility'] and by.get('Fri')[0] == 'Barbell bench press'
   and days[5]['exercises'][0]['sets'] == 10 and days[5]['exercises'][0]['reps'] == '12' and by.get('Sun') == ['Light walk'])
n = plan.get('notes', '')
ok('mark.json: notes cover load choice, progression, steps and diet', all(s in n for s in ('last 2 reps', '2.5kg', '5kg', '8-10k', 'calorie deficit', 'protein')))
ok('mark.json: Tue is a 20-25 min circuit', '20-25 min' in days[1].get('notes', '') and '90s' in days[1].get('notes', '') and 'Breathing hard but controlled' in days[1].get('notes', ''))
try:
    changed = subprocess.run(['git', '-C', ROOT, 'diff', '--name-only', 'HEAD', '--', 'plans/tom.json', 'plans/nikki.json', 'plans/elspeth.json', 'plans/neil.json'], capture_output=True, text=True).stdout.strip()
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

    ctx = context(); pg = page(ctx, 'link'); pg.clock.install(time='2026-10-26T09:00:00Z')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.goto(BASE + '?p=mark'); pg.wait_for_function("window.__proplog&&window.__proplog.profile==='mark'&&window.__proplog.plan", timeout=8000)
    ok('?p=mark opens Mark and remembers it', pg.evaluate("localStorage.getItem('proplog.profile')") == 'mark' and pg.inner_text('#profName') == 'Mark')
    ok('?p=mark removed from the URL', '?p=' not in pg.url, pg.url)
    ok('plan loaded from network for Mark', pg.evaluate('window.__proplog.planSource') == 'network' and pg.evaluate('window.__proplog.plan.athlete') == 'Mark' and pg.evaluate('window.__proplog.plan.author') == 'Mark Workout Bot')
    ok('plan cached under proplog.plan:mark only', pg.evaluate("!!localStorage.getItem('proplog.plan:mark')&&!localStorage.getItem('proplog.plan:neil')&&!localStorage.getItem('proplog.plan:tom')"))
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    body = pg.inner_text('#planBody')
    ok('Plan tab shows Mark title, Strength A and the notes', 'get stronger and lose weight' in body.lower() and 'Strength A' in body and '2.5kg' in body and '8-10k' in body, body[:400])
    pg.locator('[data-start=Mon]').click(); pg.wait_for_timeout(300)
    d = pg.evaluate("JSON.parse(localStorage.getItem('proplog.draft.v1:mark'))")
    names = [e.get('name') for e in (d or {}).get('exercises', [])]
    ok('Start Monday pre-fills the squat session as Lower strength', d and d.get('type') == 'Lower strength' and names[0] == 'Barbell back squat' and len(names) == 6 and len(d['exercises'][0]['sets']) == 4, names)
    ok('draft stored only under :mark', pg.evaluate("!localStorage.getItem('proplog.draft.v1:tom')||JSON.parse(localStorage.getItem('proplog.draft.v1:tom')).exercises.length===0"))
    ctx.close()

    ctx = context(); pg = page(ctx, 'picker')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.reload(); pg.wait_for_selector('#profileSheet:not(.hidden)')
    btns = pg.locator('#profGrid [data-prof]').evaluate_all("bs=>bs.map(b=>[b.dataset.prof,b.innerText.replace(/\\s+/g,' ').trim()])")
    ok('first run picker lists five profiles ending with Mark', [x[0] for x in btns] == ['tom', 'nikki', 'elspeth', 'neil', 'mark'] and 'Mark' in btns[4][1] and '0 sessions' in btns[4][1], btns)
    layout = pg.evaluate("""() => {
      const g = document.getElementById('profGrid');
      const bs = [...g.querySelectorAll('[data-prof]')].map(b => b.getBoundingClientRect());
      const gr = g.getBoundingClientRect();
      return {cols: getComputedStyle(g).gridTemplateColumns.split(' ').length,
        widths: bs.map(r => Math.round(r.width)),
        tops: bs.map(r => Math.round(r.top)),
        markMid: (bs[4].left + bs[4].right) / 2, gridMid: (gr.left + gr.right) / 2, gridW: gr.width};
    }""")
    ok('five profiles stay a tidy 2-column grid with Mark centred', layout['cols'] == 2 and layout['tops'][0] == layout['tops'][1]
       and layout['tops'][4] > layout['tops'][3] and abs(layout['markMid'] - layout['gridMid']) < 8
       and abs(layout['widths'][4] - layout['widths'][0]) <= 2 and layout['widths'][4] < layout['gridW'] * 0.7, layout)
    pg.click('#profGrid [data-prof=mark]'); pg.wait_for_function("window.__proplog.profile==='mark'")
    ok('picking Mark shows an empty log', pg.evaluate('window.__proplog.db.sessions.length') == 0)
    ctx.close()

    ctx = context(); pushed, gets, auth = [], [], []
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/auth/v1/token' in r.url:
            auth.append((r.url, json.loads(r.post_data or '{}')))
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps({'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600, 'user': {'id': 'u-mark', 'email': 'mark@example.com'}}))
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET':
            gets.append(r.url); return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST':
            pushed.extend(json.loads(r.post_data)); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb); pg = page(ctx, 'sync')
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','mark')")
    pg.evaluate("localStorage.setItem('proplog.v1:mark',JSON.stringify({version:1,sessions:[],bodyweight:[{id:'m1',date:'2026-10-28',kg:90,updatedAt:Date.now()}]}))")
    pg.reload(); pg.wait_for_function("window.__proplog.profile==='mark'")
    pg.click('#tabs button[data-view=data]'); pg.fill('#syncEmail', 'mark@example.com'); pg.fill('#syncPass', 'Mark-Test-Pass-1'); pg.click('#syncSignIn')
    pg.wait_for_function("JSON.parse(localStorage.getItem('proplog.sync:mark')||'{}').lastSync", timeout=8000); pg.wait_for_timeout(500)
    ok('sign-in uses email + password grant', auth and 'grant_type=password' in auth[0][0] and auth[0][1].get('email') == 'mark@example.com' and auth[0][1].get('password') == 'Mark-Test-Pass-1', [a[0] for a in auth])
    ok('session stored under proplog.sync:mark only', pg.evaluate("!!JSON.parse(localStorage.getItem('proplog.sync:mark')).session&&!(JSON.parse(localStorage.getItem('proplog.sync:neil')||'{}').session)"))
    ok('pull queries profile=eq.mark only', gets and all('profile=eq.mark' in u for u in gets), gets)
    ok('push rows are profile mark', pushed and all(x['profile'] == 'mark' and x['user_id'] == 'u-mark' for x in pushed) and any(x['kind'] == 'bodyweight' and x['data'].get('id') == 'm1' for x in pushed), pushed)
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
