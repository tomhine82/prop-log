"""v12 cardio / timed exercises: time (mm:ss or minutes), km, kcal, avg HR per entry.
Unit checks of the helpers, the Log tab (auto mode from the name, switch, inputs, totals), save format,
old weights sessions untouched, History, Progress, sync payload, share text, the plan editor ("Log as",
duration, distance) and starting a session from the plan. Needs the site at http://localhost:8766/prop-log/.
Supabase is fully mocked – no network, no real keys."""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'; SHOTS = os.path.join(ROOT, 'screenshots') + '/'
OUT_SHOT = os.environ.get('CARDIO_SHOT', '/workspace/v12-cardio.png')
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', read('config.js')).group(1)
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:600]))

ok('sw cache proplog-v12', "const CACHE = 'proplog-v12';" in read('sw.js'))
ok('PLAN-FORMAT documents cardio fields', all(k in read('PLAN-FORMAT.md') for k in ('"type": "cardio"', 'metrics', 'duration', 'distanceKm')))

NOW = int(time.time() * 1000)
OLD = {'id': 'old1', 'date': '2026-10-20', 'type': 'Gym – lower', 'exercises': [
    {'name': 'Back squat', 'sets': [{'reps': 5, 'weight': 140}, {'reps': 5, 'weight': 145}]},
    {'name': 'Rowing', 'sets': [{'reps': 10, 'weight': 60}]}],          # weights logged under a cardio-ish name (v11)
    'feel': 4, 'rpe': 7, 'notes': 'old', 'createdAt': NOW - 9e8, 'updatedAt': NOW - 9e8}
PREV_RUN = {'id': 'run0', 'date': '2026-10-25', 'type': 'Conditioning', 'exercises': [
    {'name': 'Easy run', 'mode': 'cardio', 'sets': [{'secs': 1680, 'km': 5, 'kcal': 330, 'hr': 150}]}],
    'feel': None, 'rpe': None, 'notes': '', 'createdAt': NOW - 5e8, 'updatedAt': NOW - 5e8}

with sync_playwright() as p:
    b = p.chromium.launch()
    def context(**kw):
        return b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale='en-GB', timezone_id='Europe/London', service_workers='block', **kw)
    def page(ctx, tag):
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'[{tag}] console: {m.text}')); pg.on('dialog', lambda d: d.accept()); return pg

    # ---------- helpers ----------
    ctx = context(); pg = page(ctx, 'unit'); pg.goto(URL); pg.wait_for_function('window.__proplog&&window.__proplog.cardio')
    modes = pg.evaluate("""() => { const a = window.__proplog.cardio.autoMode; return Object.fromEntries([
      'Easy run','Jog','Turbo bike','Assault bike','Recumbent bike','Cycle','Rowing machine','Rower','Row','Swim','Brisk walk','Dog walk','Treadmill walk',
      'Ski erg','SkiErg','Conditioning','Hill sprints','Intervals','Aqua aerobics',
      'Back squat','Dumbbell row','Seated cable row','Barbell bent-over row','Inverted row (barbell in rack)','One-arm dumbbell row','Dumbbell walking lunge',
      "Farmer's carry",'Kettlebell swing','Bench press','Pull-up'].map(n => [n, a(n)])); }""")
    cardio_names = ['Easy run','Jog','Turbo bike','Assault bike','Recumbent bike','Cycle','Rowing machine','Rower','Row','Swim','Brisk walk','Dog walk','Treadmill walk','Ski erg','SkiErg','Conditioning','Hill sprints','Intervals','Aqua aerobics']
    ok('autoMode: cardio names', all(modes[n] == 'cardio' for n in cardio_names), {n: modes[n] for n in cardio_names if modes[n] != 'cardio'})
    ok('autoMode: weights names (incl. rows, walking lunge, carries)', all(v == 'strength' for n, v in modes.items() if n not in cardio_names), {n: v for n, v in modes.items() if n not in cardio_names and v != 'strength'})
    durs = pg.evaluate("""() => { const f = window.__proplog.cardio.parseDur; return ['25:30','1:05:00','25','25.5','25 min','90s','1h 10m','0','','abc','-5','12:3'].map(f); }""")
    ok('parseDur: mm:ss, h:mm:ss, minutes, units; rejects junk', durs == [1530, 3900, 1500, 1530, 1500, 90, 4200, None, None, None, None, 723], durs)
    ok('fmtDur', pg.evaluate("[95,1530,3900].map(window.__proplog.cardio.fmtDur)") == ['1:35', '25:30', '1:05:00'])
    ne = pg.evaluate("""() => { const n = window.__proplog.cardio.normEx; return [
      n({name:'Back squat',sets:[{reps:'5',weight:'140'}]}),
      n({name:'Rowing',sets:[{reps:10,weight:60}]}),
      n({name:'Easy run',sets:[{secs:'1530',km:'5.004',kcal:'320.4',hr:'148'}]}),
      n({name:'Sled push',mode:'cardio',metrics:['Time','kcal','junk'],sets:[{secs:300}]}),
      n({name:'Rower',mode:'strength',sets:[{reps:20,weight:null}]}) ]; }""")
    ok('normEx: weights unchanged shape', ne[0] == {'name': 'Back squat', 'sets': [{'reps': 5, 'weight': 140}]} and ne[1] == {'name': 'Rowing', 'sets': [{'reps': 10, 'weight': 60}]}, ne[:2])
    ok('normEx: cardio entry', ne[2] == {'name': 'Easy run', 'mode': 'cardio', 'sets': [{'secs': 1530, 'km': 5.004, 'kcal': 320, 'hr': 148}]}, ne[2])
    ok('normEx: explicit cardio + metrics normalised', ne[3] == {'name': 'Sled push', 'mode': 'cardio', 'metrics': ['time', 'calories'], 'sets': [{'secs': 300, 'km': None, 'kcal': None, 'hr': None}]}, ne[3])
    ok('normEx: explicit weights override on a cardio name kept', ne[4] == {'name': 'Rower', 'mode': 'strength', 'sets': [{'reps': 20, 'weight': None}]}, ne[4])
    tot = pg.evaluate("window.__proplog.cardio.cardioTotals([{secs:600,km:2,kcal:100,hr:140},{secs:1200,km:5,kcal:200,hr:155},{secs:null,km:null,kcal:null,hr:null}])")
    ok('cardioTotals: sums, time-weighted HR, best pace', tot['secs'] == 1800 and tot['km'] == 7 and tot['kcal'] == 300 and tot['hr'] == 150 and tot['best'] == 240 and tot['n'] == 2, tot)
    ctx.close()

    # ---------- Log tab, save, history, progress, sync ----------
    ctx = context(); pushed = []
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET': return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST': pushed.extend(json.loads(r.post_data)); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb); pg = page(ctx, 'log')
    pg.goto(URL); pg.evaluate('localStorage.clear()')
    sess = {'session': {'access_token': 'at', 'refresh_token': 'rt', 'expires_at': int(time.time()) + 3600, 'user': {'id': 'u-tom', 'email': 'tom@example.com'}}, 'linkedUser': 'u-tom'}
    pg.evaluate(f"""localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','tom');
      localStorage.setItem('proplog.v1:tom',{json.dumps(json.dumps({'version': 1, 'sessions': [OLD, PREV_RUN], 'bodyweight': []}))});
      localStorage.setItem('proplog.sync:tom',{json.dumps(json.dumps(sess))})""")
    pg.reload(); pg.wait_for_function('window.__proplog&&window.__proplog.db.sessions.length===2')
    old_before = [s for s in pg.evaluate('window.__proplog.db.sessions') if s['id'] == 'old1'][0]
    ok('old v11 session loads unchanged', old_before['exercises'] == OLD['exercises'], old_before['exercises'])
    pg.wait_for_timeout(800); pushed.clear()

    def add(name):
        pg.select_option('#exPick', '__custom'); pg.fill('#exCustom', name); pg.click('#addEx')
    pg.click('#tabs button[data-view=log]')
    pg.select_option('#sType', index=0)
    add('Easy run')
    card = pg.locator('#exList .ex').last
    ok('Log: "Easy run" opens in time & distance mode', card.get_attribute('data-mode') == 'cardio' and card.locator('.mode-sw button[data-mode=cardio]').get_attribute('aria-pressed') == 'true')
    ok('Log: cardio inputs time, km, kcal, avg HR', [card.locator(f'input[data-f={f}]').count() for f in ('secs', 'km', 'kcal', 'hr')] == [1, 1, 1, 1] and card.locator('input[data-f=reps]').count() == 0)
    ok('Log: last run shown + used as placeholders', 'Last (' in card.inner_text() and '28:00' in card.inner_text() and card.locator('input[data-f=secs]').get_attribute('placeholder') == '28:00')
    card.locator('input[data-f=secs]').fill('25:30'); card.locator('input[data-f=secs]').press('Tab')
    card.locator('input[data-f=km]').fill('5'); card.locator('input[data-f=kcal]').fill('320'); card.locator('input[data-f=hr]').fill('148')
    card.locator('[data-act=addSet]').click(); card = pg.locator('#exList .ex').nth(0)
    t2 = card.locator('input[data-f=secs]').nth(1); t2.fill('12'); t2.press('Tab')
    card = pg.locator('#exList .ex').nth(0)
    ok('Log: minutes typed as "12" become 12:00', card.locator('input[data-f=secs]').nth(1).input_value() == '12:00', card.locator('input[data-f=secs]').nth(1).input_value())
    card.locator('input[data-f=km]').nth(1).fill('2')
    bad = card.locator('input[data-f=secs]').nth(1); bad.fill('abc'); bad.press('Tab')
    ok('Log: unparseable time flagged', 'bad' in (pg.locator('#exList .ex').nth(0).locator('input[data-f=secs]').nth(1).get_attribute('class') or ''))
    bad = pg.locator('#exList .ex').nth(0).locator('input[data-f=secs]').nth(1); bad.fill('11:00'); bad.press('Tab')
    pg.locator('#exList .ex').nth(0).locator('input[data-f=kcal]').nth(1).click()
    summ = pg.locator('#exList .ex').nth(0).locator('.cardio-sum').inner_text() if pg.locator('#exList .ex').nth(0).locator('.cardio-sum').count() else ''
    ok('Log: total + best pace line', '7 km' in summ and '36:30' in summ and '5:06/km' in summ, summ)

    add('Bench press'); bp = pg.locator('#exList .ex').nth(1)
    ok('Log: weights exercise keeps reps/kg grid', bp.get_attribute('data-mode') == 'strength' and bp.locator('input[data-f=reps]').count() == 1 and bp.locator('input[data-f=secs]').count() == 0)
    bp.locator('input[data-f=reps]').fill('5'); bp.locator('input[data-f=weight]').fill('100')

    add('Sled push'); sp = pg.locator('#exList .ex').nth(2)
    ok('Log: unknown name defaults to reps & kg', sp.get_attribute('data-mode') == 'strength')
    sp.locator('.mode-sw button[data-mode=cardio]').click(); sp = pg.locator('#exList .ex').nth(2)
    ok('Log: switch to time & distance', sp.get_attribute('data-mode') == 'cardio' and sp.locator('input[data-f=secs]').count() == 1)
    sp.locator('input[data-f=secs]').fill('4:00'); sp.locator('input[data-f=kcal]').fill('60'); sp.locator('input[data-f=kcal]').press('Tab')
    pg.evaluate("document.activeElement&&document.activeElement.blur();document.querySelector('#toast').classList.remove('show')")
    pg.evaluate('window.scrollTo(0, document.querySelector("#exList").getBoundingClientRect().top + window.scrollY - 80)'); pg.wait_for_timeout(400)
    pg.screenshot(path=OUT_SHOT); pg.screenshot(path=SHOTS + 'cardio-log.png')
    ok('screenshot written', os.path.getsize(OUT_SHOT) > 10000)

    pg.click('#saveSession'); pg.wait_for_function("window.__proplog.db.sessions.length===3")
    s = [x for x in pg.evaluate('window.__proplog.db.sessions') if x['id'] not in ('old1', 'run0')][0]
    exs = {e['name']: e for e in s['exercises']}
    ok('Save: cardio entries stored as time/km/kcal/HR', exs['Easy run'] == {'name': 'Easy run', 'mode': 'cardio', 'sets': [{'secs': 1530, 'km': 5, 'kcal': 320, 'hr': 148}, {'secs': 660, 'km': 2, 'kcal': None, 'hr': None}]}, exs.get('Easy run'))
    ok('Save: weights exercise unchanged format', exs['Bench press'] == {'name': 'Bench press', 'sets': [{'reps': 5, 'weight': 100}]}, exs.get('Bench press'))
    ok('Save: switched exercise saved as cardio', exs['Sled push'] == {'name': 'Sled push', 'mode': 'cardio', 'sets': [{'secs': 240, 'km': None, 'kcal': 60, 'hr': None}]}, exs.get('Sled push'))
    ok('Save: old session untouched', [x for x in pg.evaluate('window.__proplog.db.sessions') if x['id'] == 'old1'][0] == old_before)

    pg.wait_for_function("document.querySelector('#histList')&&document.querySelector('#histList').innerText.length>0")
    hist = pg.inner_text('#histList')
    ok('History: cardio line with km, time, kcal, HR', '7 km' in hist and '40:30' in hist and '380 kcal' in hist and 'HR' in hist, hist)
    ok('History: weights sessions still show sets', 'Back squat' in hist or 'set' in hist.lower(), hist)

    for _ in range(40):
        if any(r['kind'] == 'session' and r['id'] == s['id'] for r in pushed): break
        pg.wait_for_timeout(150)
    row = [r for r in pushed if r['kind'] == 'session' and r['id'] == s['id']]
    ok('Sync: session pushed with cardio fields', row and {e['name']: e for e in row[-1]['data']['exercises']}['Easy run']['sets'][0] == {'secs': 1530, 'km': 5, 'kcal': 320, 'hr': 148}, row)
    ok('Sync: old session data unchanged in any push', all(r['data']['exercises'] == OLD['exercises'] for r in pushed if r['id'] == 'old1'), [r for r in pushed if r['id'] == 'old1'])

    pg.click('#tabs button[data-view=progress]'); pg.select_option('#progEx', 'Easy run'); pg.wait_for_selector('#cardioStats')
    st = pg.inner_text('#cardioStats')
    ok('Progress: cardio stats (total km, time, best pace)', '12' in st and '5:06' in st, st)
    pg.screenshot(path=SHOTS + 'cardio-progress.png', full_page=True)
    pg.select_option('#progEx', 'Back squat')
    ok('Progress: weights exercise still uses kg chart', pg.locator('#cardioStats').count() == 0)
    share = str(pg.evaluate("window.__proplog.buildShare(7)"))
    ok('Share text: cardio entry with time, km, kcal, HR, pace', 'Easy run' in share and '25:30 · 5 km · 320 kcal · HR 148 · 5:06/km' in share and 'cardio = time' in share, share)
    ok('Share text: weights still reps × kg', 'Bench press' in share and '100' in share, share)

    # reopen the saved session from History: modes kept, values formatted
    pg.click('#tabs button[data-view=history]')
    pg.locator('#histList li').first.click(); pg.wait_for_timeout(300)
    ed = pg.locator('[data-act=edit], .edit-btn, button:has-text("Edit")')
    if ed.count(): ed.first.click()
    pg.wait_for_timeout(300)
    if pg.locator('#exList .ex[data-mode=cardio]').count():
        ok('Edit: reopened session shows cardio values', pg.locator('#exList .ex[data-mode=cardio] input[data-f=secs]').first.input_value() == '25:30')
    ctx.close()

    # ---------- plan editor + start from plan (Nikki: Turbo bike) ----------
    ctx = context(); pg = page(ctx, 'plan'); pg.clock.install(time='2026-10-27T09:00:00Z')   # a Tuesday
    pg.goto(URL); pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.goto(BASE + '?p=nikki'); pg.wait_for_function("window.__proplog&&window.__proplog.profile==='nikki'&&window.__proplog.plan", timeout=8000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_selector('#editPlan')
    view = pg.inner_text('#view-plan') if pg.query_selector('#view-plan') else pg.inner_text('body')
    ok('Plan view: Turbo bike keeps "1 × 20-25 min"', '1 × 20-25 min' in view, view[:800])
    pg.click('#editPlan'); pg.wait_for_selector('#coachNote')
    row = pg.locator('.ped[data-day=Tue] .ex').filter(has=pg.locator('input[data-field=name][value="Turbo bike"]'))
    ok('Editor: Turbo bike "Log as" defaults to cardio with duration + distance', row.locator('select[data-field=mode]').input_value() == 'cardio'
       and row.locator('input[data-field=duration]').count() == 1 and row.locator('input[data-field=dist]').count() == 1 and row.locator('input[data-field=reps]').count() == 0)
    row.locator('input[data-field=duration]').fill('30 min'); row.locator('input[data-field=dist]').fill('12')
    mon = pg.locator('.ped[data-day=Mon] .ex').filter(has=pg.locator('input[data-field=name][value="Glute bridge"]'))
    ok('Editor: weights exercise shows reps/target kg', mon.locator('select[data-field=mode]').input_value() == 'strength' and mon.locator('input[data-field=reps]').count() == 1)
    pg.locator('.ped[data-day=Sun] [data-add]').click()
    nw = pg.locator('.ped[data-day=Sun] .ex').last; nw.locator('input[data-field=name]').fill('Swim'); nw.locator('input[data-field=name]').press('Tab')
    nw = pg.locator('.ped[data-day=Sun] .ex').last
    ok('Editor: new exercise named "Swim" flips to cardio', nw.locator('select[data-field=mode]').input_value() == 'cardio', nw.inner_html()[:300])
    pg.click('#planSave'); pg.wait_for_selector('#planEditedTag')
    pe = pg.evaluate('window.__proplog.planEdit')
    days = {d['day']: d for d in pe['plan']['weeks'][0]['days']} if pe and 'plan' in pe else {}
    tb = days.get('Tue', {}).get('exercises', [{}])[0]
    ok('Editor: saved plan keeps cardio (by name), duration, distanceKm', tb.get('type', 'cardio') == 'cardio' and pg.evaluate('n=>window.__proplog.cardio.planExMode(n)', tb) == 'cardio' and tb.get('duration') == '30 min' and tb.get('distanceKm') == 12, tb)
    gb = days.get('Mon', {}).get('exercises', [{}])[0]
    sw_ = days.get('Sun', {}).get('exercises', [{}])
    ok('Editor: new Swim saved and logs as cardio', sw_ and sw_[-1].get('name') == 'Swim' and pg.evaluate('n=>window.__proplog.cardio.planExMode(n)', sw_[-1]) == 'cardio', sw_)
    rk = pg.locator('.ped[data-day=Sat] .ex').first
    ok('Editor: weights exercise saved without cardio fields', not any(k in gb for k in ('type', 'duration', 'distanceKm', 'metrics')), gb)
    pg.wait_for_selector('[data-start=Tue]')
    view = pg.inner_text('body')
    ok('Plan view: shows edited cardio target', '30 min' in view and '12 km' in view)
    pg.click('[data-start=Tue]'); pg.wait_for_selector('#exList .ex')
    c = pg.locator('#exList .ex').first
    ok('Start from plan: Turbo bike opens in cardio mode with plan placeholders', c.get_attribute('data-mode') == 'cardio' and c.locator('input[data-f=secs]').get_attribute('placeholder') == '30 min'
       and c.locator('input[data-f=km]').get_attribute('placeholder') == '12', c.inner_html()[:400])
    pg.screenshot(path=SHOTS + 'cardio-from-plan.png')
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
