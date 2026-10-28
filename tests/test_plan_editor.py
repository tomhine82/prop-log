"""In-app plan editor (v11): edit, save, reload, reset, changes list, profile separation,
newer-coach-plan banner, and Supabase kind 'plan' (including the 400 check-constraint fallback).
Static checks run anywhere; the browser part needs the site at http://localhost:8766/prop-log/.
Supabase is fully mocked – no network, no real keys."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:500]))
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()

html, sw, sql = read('index.html'), read('sw.js'), read('supabase/plan_edits.sql')
ok('sw cache proplog-v11', "const CACHE = 'proplog-v11';" in sw)
ok('plan edits stored per profile', "planEdit:'proplog.planEdit:'+id" in html)
ok('no service key in the frontend', not re.search(r'service_role|sb_secret_|SUPABASE_SERVICE_KEY', html + sw + read('config.js')))
ok('plan_edits.sql widens the kind check and leaves RLS alone',
   'drop constraint if exists proplog_data_kind_chk' in sql and "kind in ('session', 'bodyweight', 'plan')" in sql
   and 'policy' not in sql.lower() and 'enable row level security' not in sql.lower())
ok('docs describe the plan row', "kind = 'plan'" in read('README.md') and 'id = \'current\'' in read('PLAN-FORMAT.md') or 'id` | `current`' in read('PLAN-FORMAT.md'))

from playwright.sync_api import sync_playwright
SB = re.search(r'"supabaseUrl":\s*"([^"]+)"', read('config.js')).group(1)
cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}

def boot(pg, profile):
    pg.goto(URL)
    pg.evaluate("localStorage.clear();localStorage.setItem('proplog.migrated.v2','1')")
    pg.goto(BASE + '?p=' + profile)
    pg.wait_for_function("window.__proplog&&window.__proplog.profile==='%s'&&window.__proplog.plan" % profile, timeout=8000)

def ex_row(pg, day, name):
    return pg.locator('.ped[data-day=%s] .ex' % day).filter(has=pg.locator('input[data-field=name][value="%s"]' % name))

def edit_mark(pg):
    pg.click('#tabs button[data-view=plan]')
    pg.wait_for_selector('#editPlan')
    pg.click('#editPlan')
    pg.wait_for_selector('#coachNote')
    ex_row(pg, 'Mon', 'Dumbbell walking lunge').locator('[data-del]').click()
    ex_row(pg, 'Mon', 'Cable face pull').locator('[data-up]').click()
    pg.locator('.ped[data-day=Mon] [data-add]').click()
    pg.locator('.ped[data-day=Mon] .ex').last.locator('input[data-field=name]').fill('Step-up')
    ex_row(pg, 'Wed', 'Barbell deadlift').locator('input[data-field=sets]').fill('3')
    pg.fill('#coachNote', 'knee sore, swap lunges')
    pg.click('#planSave')
    pg.wait_for_selector('#planEditedTag')

with sync_playwright() as p:
    b = p.chromium.launch()
    def context(**kw):
        return b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='en-GB', timezone_id='Europe/London', service_workers='block', **kw)
    def page(ctx, tag):
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'[{tag}] console: {m.text}')); pg.on('dialog', lambda d: d.accept()); return pg

    # reorder helper, independent of the saved Mark plan
    ctx = context(); pg = page(ctx, 'diff'); pg.clock.install(time='2026-10-26T09:00:00Z')
    boot(pg, 'mark')
    lines = pg.evaluate("""() => window.__proplog.planChanges(
      {weeks:[{days:[{day:'Mon',title:'A',type:'Lower strength',exercises:[{name:'Squat',sets:4,reps:'6'},{name:'Row',sets:3,reps:'8'}]}]}]},
      {weeks:[{days:[{day:'Mon',title:'A',type:'Lower strength',exercises:[{name:'Row',sets:3,reps:'8'},{name:'Squat',sets:4,reps:'6'}]}]}]})""")
    ok('changes list: reordered exercises', lines == ['Mon: reordered exercises'], lines)
    ctx.close()

    ctx = context(); pg = page(ctx, 'edit'); pg.clock.install(time='2026-10-26T09:00:00Z')
    boot(pg, 'mark')
    edit_mark(pg)
    saved = json.loads(pg.evaluate("localStorage.getItem('proplog.planEdit:mark')"))
    changes = saved.get('changes') or []
    ok('changes list: removed lunge, deadlift dose, added step-up, coach note',
       'Mon: removed Dumbbell walking lunge' in changes and 'Wed: Barbell deadlift 4x5 -> 3x5' in changes
       and 'Mon: added Step-up 3x8' in changes and 'Mon: reordered exercises' in changes
       and 'Note to coach: knee sore, swap lunges' in changes and saved.get('coachNote') == 'knee sore, swap lunges'
       and saved.get('basedOnUpdated') == '2026-10-28' and saved.get('plan', {}).get('athlete') == 'Mark', changes)
    ok('edited tag shows', 'Edited by you' in pg.inner_text('#planEditedTag'))
    mon = pg.inner_text('details[data-day=Mon]')
    ok('plan tab uses the edit (no lunge, step-up, how-to still there)', 'Dumbbell walking lunge' not in mon and 'Step-up' in mon and 'How to' in mon, mon[:500])
    pg.locator('[data-start=Mon]').click(); pg.wait_for_timeout(300)
    draft = json.loads(pg.evaluate("localStorage.getItem('proplog.draft.v1:mark')"))
    names = [e.get('name') for e in draft.get('exercises', [])]
    ok('start session uses the edited plan', names[0] == 'Barbell back squat' and 'Dumbbell walking lunge' not in names and 'Step-up' in names and draft.get('type') == 'Lower strength', names)
    pg.reload(); pg.wait_for_function("window.__proplog.planEdit&&window.__proplog.planEdit.coachNote==='knee sore, swap lunges'", timeout=8000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_selector('#planEditedTag')
    mon = pg.inner_text('details[data-day=Mon]')
    ok('reload keeps the edit', 'Dumbbell walking lunge' not in mon and 'Step-up' in mon, mon[:500])
    pg.click('#planReset'); pg.wait_for_function("!localStorage.getItem('proplog.planEdit:mark')", timeout=5000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(200)
    ok('reset restores the coach plan', 'Dumbbell walking lunge' in pg.inner_text('#planBody') and pg.locator('#planEditedTag').count() == 0)
    ctx.close()

    ctx = context(); pg = page(ctx, 'sep'); pg.clock.install(time='2026-10-26T09:00:00Z')
    boot(pg, 'mark'); edit_mark(pg)
    pg.click('#profileBtn'); pg.click('#profGrid [data-prof=neil]')
    pg.wait_for_function("window.__proplog.profile==='neil'&&window.__proplog.plan&&window.__proplog.plan.athlete==='Neil'", timeout=8000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    ok('neil is not edited', pg.locator('#planEditedTag').count() == 0 and not pg.evaluate("localStorage.getItem('proplog.planEdit:neil')"))
    ok('mark edit stays in his own key', json.loads(pg.evaluate("localStorage.getItem('proplog.planEdit:mark')"))['coachNote'] == 'knee sore, swap lunges')
    ctx.close()

    ctx = context(); pg = page(ctx, 'banner'); pg.clock.install(time='2026-10-26T09:00:00Z')
    boot(pg, 'mark'); edit_mark(pg)
    newer = json.loads(read('plans/mark.json')); newer['updated'] = '2026-11-04'
    ctx.route('**/plans/mark.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(newer)))
    pg.reload(); pg.wait_for_function("window.__proplog.coachPlan", timeout=8000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_selector('#coachBanner', timeout=8000)
    ok('newer coach plan banner', 'Your coach sent a new plan' in pg.inner_text('#coachBanner') and 'Dumbbell walking lunge' not in pg.inner_text('details[data-day=Mon]'))
    pg.click('#keepEdits'); pg.wait_for_selector('#coachBanner', state='detached')
    kept = json.loads(pg.evaluate("localStorage.getItem('proplog.planEdit:mark')"))
    ok('keep my edits hides the banner and keeps the edit', kept['basedOnUpdated'] == '2026-11-04' and 'Dumbbell walking lunge' not in pg.inner_text('details[data-day=Mon]'))
    newer['updated'] = '2026-11-11'
    pg.reload(); pg.click('#tabs button[data-view=plan]'); pg.wait_for_selector('#coachBanner', timeout=8000)
    pg.click('#useNewPlan'); pg.wait_for_function("!localStorage.getItem('proplog.planEdit:mark')", timeout=5000)
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    ok('use new plan drops the edit', pg.locator('#coachBanner').count() == 0 and 'Dumbbell walking lunge' in pg.inner_text('#planBody'))
    ctx.close()

    ctx = context(); pushed, gets, auth = [], [], []
    state = {'allow_plan': False}
    def sb(route):
        r = route.request
        if r.method == 'OPTIONS': return route.fulfill(status=200, headers=cors)
        if '/auth/v1/token' in r.url:
            auth.append(r.url)
            return route.fulfill(status=200, headers=cors, content_type='application/json', body=json.dumps({'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 3600, 'user': {'id': 'u-mark', 'email': 'mark@example.com'}}))
        if '/rest/v1/proplog_data' in r.url and r.method == 'GET':
            gets.append(r.url); return route.fulfill(status=200, headers=cors, content_type='application/json', body='[]')
        if '/rest/v1/proplog_data' in r.url and r.method == 'POST':
            rows = json.loads(r.post_data or '[]')
            if any(x.get('kind') == 'plan' for x in rows) and not state['allow_plan']:
                return route.fulfill(status=400, headers=cors, content_type='application/json',
                    body=json.dumps({'code': '23514', 'message': 'new row violates check constraint "proplog_data_kind_chk"'}))
            pushed.extend(rows); return route.fulfill(status=201, headers=cors, body='')
        return route.fulfill(status=404, headers=cors, content_type='application/json', body='{}')
    ctx.route(SB + '/**', sb); pg = page(ctx, 'sync'); pg.clock.install(time='2026-10-26T09:00:00Z')
    boot(pg, 'mark')
    pg.click('#tabs button[data-view=data]'); pg.fill('#syncEmail', 'mark@example.com'); pg.fill('#syncPass', 'Mark-Test-Pass-1'); pg.click('#syncSignIn')
    pg.wait_for_function("JSON.parse(localStorage.getItem('proplog.sync:mark')||'{}').lastSync", timeout=8000)
    edit_mark(pg)
    pg.wait_for_selector('#planLocalNote', timeout=8000)
    sync_state = json.loads(pg.evaluate("localStorage.getItem('proplog.sync:mark')"))
    ok('constraint rejection keeps the edit and says saved on this device',
       'Saved on this device' in pg.inner_text('#planLocalNote') and sync_state.get('planBlocked') is True
       and 'plan:current' in sync_state.get('queue', []) and json.loads(pg.evaluate("localStorage.getItem('proplog.planEdit:mark')"))['coachNote'] == 'knee sore, swap lunges'
       and not any(x.get('kind') == 'plan' for x in pushed), sync_state.get('queue'))
    ok('pull stayed on profile mark', gets and all('profile=eq.mark' in u for u in gets), gets)
    state['allow_plan'] = True
    pg.evaluate("window.__plSync.sync()")
    pg.wait_for_function("!JSON.parse(localStorage.getItem('proplog.sync:mark')||'{}').planBlocked", timeout=8000)
    pg.wait_for_selector('#planLocalNote', state='detached')
    plans = [x for x in pushed if x.get('kind') == 'plan']
    ok('retry uploads kind plan id current for this profile', len(plans) == 1 and plans[0]['id'] == 'current' and plans[0]['profile'] == 'mark'
       and plans[0]['data']['coachNote'] == 'knee sore, swap lunges' and 'Mon: removed Dumbbell walking lunge' in plans[0]['data']['changes']
       and plans[0]['data']['basedOnUpdated'] == '2026-10-28' and 'editedAt' in plans[0]['data'] and plans[0].get('deleted') is False, plans)
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
