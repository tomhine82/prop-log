"""v13 regression: reps that were 'saved' but never stored (Nikki, Fri 30 Oct 2026, Strength A).
v9-v12 put the plan's reps ("10", "10 each side", "30m") in the empty reps boxes as a near-white bold
placeholder, so the boxes looked filled in; only the kg she typed was stored. Checks: empty boxes look
empty, 'Use plan' fills only empty boxes, kg-without-reps asks before saving, typed reps are kept when
Save is tapped straight away (focus still in the box, no blur/change), boxes are read again on Save,
a newer synced copy never blanks numbers this device has (and the merged copy is re-uploaded), a stale
edit keeps newer saved numbers, and Nikki's real stored sessions load unchanged.
Needs the site at http://localhost:8766/prop-log/. Supabase and the plan are mocked - no network, no keys."""
import json, os, re, time
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'http://localhost:8766/prop-log/index.html'
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', read('config.js')).group(1)
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:600]))

ok('sw cache proplog-v14', "const CACHE = 'proplog-v14';" in read('sw.js'))

X = lambda n, s, r, kg=None: {'name': n, 'sets': s, 'reps': r, 'targetKg': kg, 'rest': '', 'notes': ''}
PLAN = {'version': 1, 'athlete': 'Nikki', 'title': 'week 1', 'updated': '2026-10-27', 'weeks': [{'label': 'Weekly plan', 'days': [
    {'day': d, 'title': 'Strength A', 'type': 'Other', 'exercises': [X('Glute bridge', 3, '12'), X('Dumbbell Romanian deadlift', 3, '10'),
     X('Dumbbell bench press', 3, '10'), X('One-arm dumbbell row', 3, '10 each side'), X("Kettlebell farmer's carry", 3, '30m'),
     X('Dead bug', 3, '8 each side'), X('Side plank', 3, '15-20s each side', 0)]} for d in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')]}]}
NOW = int(time.time() * 1000)
# Nikki's stored rows as they are in Supabase (trimmed): Wed with reps, Fri with kg and reps null
WED = {'id': 'mvscsn12p09uy', 'date': '2026-10-28', 'type': 'Other', 'feel': 3, 'rpe': 5, 'notes': '', 'createdAt': NOW - 9e8, 'updatedAt': NOW - 9e8,
       'exercises': [{'name': 'Kettlebell deadlift', 'sets': [{'reps': 10, 'weight': 12}, {'reps': 12, 'weight': 12}, {'reps': 14, 'weight': 12}]},
                     {'name': 'Side plank', 'sets': [{'reps': 20, 'weight': None}, {'reps': 15, 'weight': None}]}]}
FRI = {'id': 'mvv79qahq9xzj', 'date': '2026-10-30', 'type': 'Other', 'feel': 3, 'rpe': 7, 'notes': '', 'createdAt': NOW - 8e8, 'updatedAt': NOW - 8e8,
       'exercises': [{'name': 'Dumbbell bench press', 'sets': [{'reps': None, 'weight': 5}, {'reps': None, 'weight': 5}]},
                     {'name': 'Dead bug', 'sets': [{'reps': 8, 'weight': 0}]}]}
SESS = {'session': {'access_token': 'at', 'refresh_token': 'rt', 'expires_at': int(time.time()) + 3600, 'user': {'id': 'u-nikki', 'email': 'n@example.com'}}, 'linkedUser': 'u-nikki'}

def iso(ms):
    ms = int(ms); return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(ms / 1000)) + '.%03dZ' % (ms % 1000)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale='en-GB',
                        timezone_id='Europe/London', service_workers='block')
    rows, pushed, dialogs, answer = [], [], [], {'v': True}
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET':
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps(rows))
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST': pushed.extend(json.loads(r.post_data)); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb)
    ctx.route('**/plans/nikki.json*', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(PLAN)))
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'console: {m.text}'))
    def on_dialog(d):
        dialogs.append(d.message); (d.accept() if answer['v'] else d.dismiss())
    pg.on('dialog', on_dialog)
    def setup(sessions, signed=False):
        pg.goto(URL); pg.evaluate('localStorage.clear()')
        pg.evaluate(f"""localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','nikki');
          localStorage.setItem('proplog.v1:nikki',{json.dumps(json.dumps({'version': 1, 'sessions': sessions, 'bodyweight': []}))});""")
        if signed: pg.evaluate(f"localStorage.setItem('proplog.sync:nikki',{json.dumps(json.dumps(SESS))})")
        pg.reload(); pg.wait_for_function("window.__proplog&&window.__proplog.plan&&window.__proplog.plan.title==='week 1'")
    def start_fri():
        pg.evaluate("document.querySelector('#tabs button[data-view=plan]').click()")
        pg.evaluate("document.querySelector('[data-start=Fri]').click()"); pg.wait_for_selector('#exList .ex')
    box = lambda ei, si, f: f'.ex[data-ei="{ei}"] input[data-si="{si}"][data-f={f}]'
    saved = lambda: pg.evaluate('window.__proplog.db.sessions')
    ex_of = lambda s, name: next(e for e in s['exercises'] if e['name'] == name)

    # ---- empty boxes look empty ----
    setup([]); start_fri()
    info = pg.evaluate(f"""(()=>{{const i=document.querySelector('{box(3, 0, "reps")}');const st=getComputedStyle(i,'::placeholder');
      const t=getComputedStyle(i);return {{ph:i.placeholder,val:i.value,pc:st.color,pw:st.fontWeight,ps:st.fontStyle,tc:t.color,tw:t.fontWeight}};}})()""")
    alpha = re.search(r'/\s*([\d.]+)\)', info['pc']) or re.search(r'rgba\([^)]*,\s*([\d.]+)\)', info['pc'])
    ok('reps box: placeholder is "reps", not the plan target', info['ph'] == 'reps' and info['val'] == '', info)
    ok('reps box: placeholder faint, light, italic (not like typed text)', alpha and float(alpha.group(1)) <= 0.6 and info['pw'] == '400' and info['ps'] == 'italic' and info['tw'] != '400', info)
    ok('plan target still shown in the hint', '10 each side' in pg.locator('.ex[data-ei="3"] .plan-hint').inner_text())
    ok('no plan text in any reps box', pg.evaluate("[...document.querySelectorAll('#exList input[data-f=reps]')].every(i=>i.placeholder==='reps'&&i.value==='')"))

    # ---- kg only, Save: asks; Cancel keeps the draft and flags the boxes ----
    for ei in (1, 2):
        for si in range(3): pg.tap(box(ei, si, 'weight')); pg.keyboard.type('5')
    answer['v'] = False; dialogs.clear(); pg.tap('#saveSession'); pg.wait_for_timeout(200)
    ok('kg without reps: asks before saving', dialogs and 'kg but no reps' in dialogs[0] and 'Dumbbell Romanian deadlift' in dialogs[0], dialogs)
    ok('Cancel: nothing saved, still on Log with the kg kept', saved() == [] and pg.input_value(box(1, 0, 'weight')) == '5' and pg.evaluate("document.querySelector('#view-log').classList.contains('active')"))
    ok('Cancel: empty reps boxes flagged', pg.locator('#exList input.need').count() == 6, pg.locator('#exList input.need').count())

    # ---- Use plan fills only the empty boxes ----
    pg.tap(box(1, 1, 'reps')); pg.keyboard.type('9')
    for ei in (1, 3, 4, 5, 6): pg.locator(f'.ex[data-ei="{ei}"] [data-act=usePlan]').tap()
    d = pg.evaluate('JSON.parse(localStorage.getItem("proplog.draft.v1:nikki"))')['exercises']
    ok('Use plan: "10" -> 10, typed 9 kept, typed kg kept', [x['reps'] for x in d[1]['sets']] == [10, 9, 10] and [x['weight'] for x in d[1]['sets']] == [5, 5, 5], d[1])
    ok('Use plan: "10 each side" -> 10, "30m" -> 30, "8 each side" -> 8, "15-20s" -> 15 (+ target 0 kg)',
       [x['reps'] for x in d[3]['sets']] == [10] * 3 and [x['reps'] for x in d[4]['sets']] == [30] * 3 and [x['reps'] for x in d[5]['sets']] == [8] * 3
       and [(x['reps'], x['weight']) for x in d[6]['sets']] == [(15, 0)] * 3, [d[3], d[4], d[5], d[6]])
    ok('no Use plan button once the boxes are full', pg.locator('.ex[data-ei="1"] [data-act=usePlan]').count() == 0)

    # ---- type reps, tap Save at once (focus still in the reps box) ----
    pg.tap(box(2, 0, 'reps')); pg.keyboard.type('11'); pg.tap(box(2, 1, 'reps')); pg.keyboard.type('12'); pg.tap(box(2, 2, 'reps')); pg.keyboard.type('13')
    ok('focus still in a reps box before Save', pg.evaluate('document.activeElement.dataset.f') == 'reps')
    answer['v'] = True; dialogs.clear(); pg.tap('#saveSession'); pg.wait_for_timeout(250)
    s = saved()
    ok('Save straight after typing keeps every rep', len(s) == 1 and [(x['reps'], x['weight']) for x in ex_of(s[0], 'Dumbbell bench press')['sets']] == [(11, 5), (12, 5), (13, 5)]
       and [x['reps'] for x in ex_of(s[0], 'Dumbbell Romanian deadlift')['sets']] == [10, 9, 10], s)
    ok('no kg-without-reps question when all reps are in', not any('no reps' in m for m in dialogs), dialogs)

    # ---- Save reads the boxes even if no input event fired ----
    setup([]); start_fri()
    pg.evaluate(f"""for(const [q,v] of [['{box(1, 0, "reps")}','10'],['{box(1, 0, "weight")}','7.5']]){{const i=document.querySelector(q);i.focus();i.value=v;}}""")
    pg.tap('#saveSession'); pg.wait_for_timeout(250); s = saved()
    ok('Save reads values that never fired input/change', s and ex_of(s[0], 'Dumbbell Romanian deadlift')['sets'] == [{'reps': 10, 'weight': 7.5}], s)

    # ---- old sessions load unchanged ----
    setup([WED, FRI])
    by = {x['id']: x for x in saved()}
    ok("Nikki's Wed reps load unchanged", by['mvscsn12p09uy']['exercises'] == WED['exercises'], by['mvscsn12p09uy']['exercises'])
    ok("Nikki's Fri (kg, reps null) loads unchanged", by['mvv79qahq9xzj']['exercises'] == FRI['exercises'], by['mvv79qahq9xzj']['exercises'])

    # ---- sync: a newer copy with empty reps never blanks ours; real changes still win ----
    local = json.loads(json.dumps(FRI)); local['exercises'][0]['sets'] = [{'reps': 10, 'weight': 5}, {'reps': 10, 'weight': 5}]
    srv = json.loads(json.dumps(FRI)); srv['updatedAt'] = NOW - 5e5; srv['exercises'][0]['sets'] = [{'reps': None, 'weight': 6}, {'reps': 12, 'weight': None}]
    srv['notes'] = 'edited elsewhere'
    rows[:] = [{'kind': 'session', 'id': FRI['id'], 'data': srv, 'updated_at': iso(NOW - 5e5), 'deleted': False, 'synced_at': '2026-11-01T21:00:00.000000+00:00'}]
    pushed.clear(); setup([local], signed=True)
    pg.evaluate("window.__proplog.sync.sync('nikki')"); pg.wait_for_function("window.__proplog.sync.state('nikki').lastSync", timeout=8000); pg.wait_for_timeout(300)
    m = next(x for x in saved() if x['id'] == FRI['id'])
    ok('merge: newer copy wins where it has numbers, ours kept where it is empty',
       m['exercises'][0]['sets'] == [{'reps': 10, 'weight': 6}, {'reps': 12, 'weight': 5}] and m['notes'] == 'edited elsewhere', m)
    up = [r for r in pushed if r['id'] == FRI['id']]
    ok('merge: merged copy re-uploaded, newer than the server copy', up and up[-1]['data']['exercises'][0]['sets'] == m['exercises'][0]['sets']
       and time.mktime(time.strptime(up[-1]['updated_at'][:19], '%Y-%m-%dT%H:%M:%S')) > time.mktime(time.strptime(iso(NOW - 5e5)[:19], '%Y-%m-%dT%H:%M:%S')), up)
    ok('merge: queue empty after sync', pg.evaluate("window.__proplog.sync.state('nikki').queue") == [])
    srv2 = json.loads(json.dumps(m)); srv2['updatedAt'] = NOW + 5e6; srv2['exercises'][0]['sets'] = [{'reps': 8, 'weight': 6}]
    rows[:] = [{'kind': 'session', 'id': FRI['id'], 'data': srv2, 'updated_at': iso(NOW + 5e6), 'deleted': False, 'synced_at': '2026-11-01T21:30:00.000000+00:00'}]
    pushed.clear(); pg.evaluate("window.__proplog.sync.sync('nikki')"); pg.wait_for_timeout(1200)
    m2 = next(x for x in saved() if x['id'] == FRI['id'])
    ok('merge: a newer copy with real numbers (and a set removed) applies as is, nothing re-uploaded',
       m2['exercises'][0]['sets'] == [{'reps': 8, 'weight': 6}] and not [r for r in pushed if r['id'] == FRI['id']], (m2, pushed))

    # ---- stale edit keeps newer saved numbers ----
    rows[:] = []; setup([FRI])
    pg.evaluate("document.querySelector('#tabs button[data-view=history]').click()")
    pg.locator(f'#histList .item[data-id="{FRI["id"]}"]').tap(); pg.wait_for_selector('#exList .ex')
    pg.evaluate(f"""(()=>{{const d=window.__proplog.db;const s=d.sessions.find(x=>x.id==='{FRI["id"]}');
      s.exercises[0].sets=[{{reps:10,weight:5}},{{reps:10,weight:5}}];s.updatedAt=Date.now()+1000;}})()""")   # e.g. a sync landed meanwhile
    pg.evaluate("document.querySelector('#sNotes').value='edit';document.querySelector('#sNotes').dispatchEvent(new Event('input',{bubbles:true}))")
    answer['v'] = True; pg.tap('#saveSession'); pg.wait_for_timeout(250)
    e = next(x for x in saved() if x['id'] == FRI['id'])
    ok('stale edit: newer saved reps kept in boxes left empty', e['exercises'][0]['sets'] == [{'reps': 10, 'weight': 5}, {'reps': 10, 'weight': 5}] and e['notes'] == 'edit', e)

    ok('no page errors', not errors, errors)
    b.close()

n = sum(1 for _, c in results if c); print(f'\n{n}/{len(results)} passed'); raise SystemExit(0 if n == len(results) else 1)
