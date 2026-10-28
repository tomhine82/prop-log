"""Theme (v9: burnt orange page, royal blue surfaces, WCAG AA text) and the per-exercise "▶ How to" YouTube links
(default search URL from the name, optional plan "video" override, URL encoding, hand-added exercises).
Static checks run anywhere; the browser part needs the site served at http://localhost:8766/prop-log/."""
import json, os, re, sys
from urllib.parse import quote, urlparse, parse_qs
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'http://localhost:8766/prop-log/'; URL = BASE + 'index.html'
results, errors = [], []
def ok(n, c, extra=''):
    results.append((n, bool(c))); print(('PASS ' if c else 'FAIL ') + n + ('' if c else ' :: ' + str(extra)[:400]))
read = lambda p: open(os.path.join(ROOT, p), encoding='utf-8').read()
def lum(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]; return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def contrast(a, b):
    a, b = lum(a), lum(b); return (max(a, b) + 0.05) / (min(a, b) + 0.05)
def rgb_hex(s):
    m = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', s); return '#%02x%02x%02x' % tuple(int(x) for x in m.groups()) if m else s

# ---------- static: palette ----------
html, wd, man = read('index.html'), read('withings.html'), json.loads(read('manifest.json'))
root = re.search(r':root\{(.*?)\n\}', html, re.S).group(1)
V = dict(re.findall(r'--([a-z0-9-]+):(#[0-9A-Fa-f]{6})', root))
ok('page background is burnt orange (#C25100)', V.get('bg', '').upper() == '#C25100', V.get('bg'))
ok('cards are royal blue (#1F3FA8), inner boxes darker blue', V.get('card', '').upper() == '#1F3FA8' and V.get('card2', '').upper() == '#183590', V)
ok('single palette: no separate dark-mode colours', 'prefers-color-scheme' not in html)
pairs = [('text', 'card'), ('text', 'card2'), ('muted', 'card'), ('muted', 'card2'), ('accent', 'card'), ('accent', 'card2'), ('accent-ink', 'accent'),
         ('blue', 'card'), ('danger', 'card'), ('danger', 'card2'), ('warn', 'card'), ('warn', 'card2'), ('on-bg', 'bg')]
low = [(a, b, round(contrast(V[a], V[b]), 2)) for a, b in pairs if contrast(V[a], V[b]) < 4.5]
ok('all text/background pairs meet WCAG AA 4.5:1', not low, low)
ok('theme-color meta is the orange', '<meta name="theme-color" content="#C25100">' in html and html.count('name="theme-color"') == 1)
ok('manifest background_color + theme_color orange', man['background_color'] == '#C25100' and man['theme_color'] == '#C25100', man)
ok('withings.html uses the same palette', '--bg:#C25100' in wd and '--card:#1F3FA8' in wd and 'prefers-color-scheme' not in wd)
ok('sw cache proplog-v10', "const CACHE = 'proplog-v10';" in read('sw.js'))
ok('plan files have no video fields yet (not edited)', all('"video"' not in read(f'plans/{p}.json') for p in ('tom', 'nikki', 'elspeth', 'neil', 'mark')))
ok('PLAN-FORMAT.md documents the video field', '"video"' in read('PLAN-FORMAT.md') and 'search_query=' in read('PLAN-FORMAT.md'))

# What videoUrl() returns (encodeURIComponent) and what a.href reads back (the browser also escapes ' as %27).
def search(name): return 'https://www.youtube.com/results?search_query=' + quote(name + ' exercise form', safe="!'()*-._~")
def href(name): return 'https://www.youtube.com/results?search_query=' + quote(name + ' exercise form', safe="!()*-._~")

# ---------- browser ----------
from playwright.sync_api import sync_playwright
VID = 'https://www.youtube.com/watch?v=abcDEF12345'
with sync_playwright() as p:
    b = p.chromium.launch()
    def context(**kw):
        return b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, locale='en-GB', timezone_id='Europe/London', service_workers='block', **kw)
    def page(ctx, tag):
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errors.append(f'[{tag}] pageerror: {e}'))
        pg.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(f'[{tag}] console: {m.text}')); pg.on('dialog', lambda d: d.accept()); return pg
    def fresh(pg, prof):
        pg.goto(URL); pg.evaluate(f"localStorage.clear();localStorage.setItem('proplog.migrated.v2','1');localStorage.setItem('proplog.profile','{prof}')")
        pg.reload(); pg.wait_for_function("window.__proplog&&window.__proplog.plan", timeout=8000)

    for scheme in ('light', 'dark'):
        ctx = context(color_scheme=scheme); pg = page(ctx, 'theme-' + scheme); fresh(pg, 'neil')
        cs = lambda sel, prop: pg.evaluate(f"getComputedStyle(document.querySelector({json.dumps(sel)})).{prop}")
        ok(f'{scheme}: body is orange, cards blue, text white', rgb_hex(cs('body', 'backgroundColor')) == '#c25100' and rgb_hex(cs('.card', 'backgroundColor')) == '#1f3fa8'
           and rgb_hex(cs('.card', 'color')) == '#ffffff', (cs('body', 'backgroundColor'), cs('.card', 'backgroundColor')))
        ok(f'{scheme}: inputs dark blue with white text', rgb_hex(cs('#sDate', 'backgroundColor')) == '#183590' and rgb_hex(cs('#sDate', 'color')) == '#ffffff')
        ok(f'{scheme}: tab bar blue, active tab light orange', rgb_hex(cs('nav.tabs', 'backgroundColor')) == '#1f3fa8' and rgb_hex(cs('nav.tabs button.on', 'color')) == '#ffb066')
        ctx.close()

    # default search links on the Plan tab (Neil, Wed = Day B) + encoding
    ctx = context(); pg = page(ctx, 'plan'); pg.clock.install(time='2026-10-30T09:00:00Z'); fresh(pg, 'neil')
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    rows = pg.locator('#planBody details[data-day=Fri] .pex').evaluate_all("rs=>rs.map(r=>{const a=r.querySelector('a.vid');return [r.querySelector('.pn span').textContent,a&&a.href,a&&a.target,a&&a.rel,a&&a.textContent]})")
    ok('plan: every exercise has a ▶ How to link', len(rows) == 6 and all(r[1] and r[4].strip() == '▶ How to' for r in rows), rows)
    ok('plan: links open in a new tab, noopener', all(r[2] == '_blank' and 'noopener' in r[3] for r in rows), rows)
    ok('plan: default link = YouTube search for "<name> exercise form"', all(parse_qs(urlparse(r[1]).query)['search_query'] == [r[0] + ' exercise form'] and r[1].startswith('https://www.youtube.com/results?search_query=') for r in rows), rows)
    vu = lambda n, v=None: pg.evaluate('([n,v])=>window.__proplog.videoUrl(n,v)', [n, v])
    fc = [r for r in rows if r[0] == "Farmer's carry"]
    ok("plan: URL encoding (spaces -> %20, apostrophe)", fc and fc[0][1] == href("Farmer's carry") and ' ' not in fc[0][1], fc)
    ok("videoUrl: Farmer's carry", vu("Farmer's carry") == search("Farmer's carry"), vu("Farmer's carry"))
    vu = lambda n, v=None: pg.evaluate('([n,v])=>window.__proplog.videoUrl(n,v)', [n, v])
    ok('videoUrl encodes & # ? / + and unicode', vu('Curl & press #2 / 50+? ½') == 'https://www.youtube.com/results?search_query=Curl%20%26%20press%20%232%20%2F%2050%2B%3F%20%C2%BD%20exercise%20form', vu('Curl & press #2 / 50+? ½'))
    ok('videoUrl trims the name', vu('  Back squat ') == search('Back squat'))
    ok('videoUrl override: direct YouTube links win', vu('Back squat', VID) == VID and vu('x', 'https://youtu.be/abc123') == 'https://youtu.be/abc123'
       and vu('x', 'https://m.youtube.com/shorts/abc') == 'https://m.youtube.com/shorts/abc')
    ok('videoUrl override: non-YouTube / unsafe values ignored', all(vu('Back squat', v) == search('Back squat') for v in ('javascript:alert(1)', 'http://www.youtube.com/watch?v=x', 'https://evil.example/youtube.com/x', 'https://youtube.com.evil.example/x', '', None)))
    ok('plan: link click does not toggle the day', pg.evaluate("document.querySelector('#planBody details[data-day=Fri]').open") is True)
    ctx.close()

    # override from the plan JSON (route a modified copy of neil.json – the file itself is not changed)
    plan = json.loads(read('plans/neil.json'))
    for w in plan['weeks']:
        for d in w['days']:
            for e in d['exercises']:
                if e['name'] == 'Seated cable row': e['video'] = VID
                if e['name'] == 'Dead bug': e['video'] = 'javascript:alert(1)'
    ctx = context(); ctx.route('**/plans/neil.json', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps(plan)))
    pg = page(ctx, 'override'); pg.clock.install(time='2026-10-30T09:00:00Z'); fresh(pg, 'neil')
    pg.click('#tabs button[data-view=plan]'); pg.wait_for_timeout(300)
    links = dict(pg.locator('#planBody details[data-day=Fri] .pex').evaluate_all("rs=>rs.map(r=>[r.querySelector('.pn span').textContent,r.querySelector('a.vid').href])"))
    ok('override: plan "video" used for that exercise', links.get('Seated cable row') == VID, links)
    ok('override: bad "video" value falls back to search', links.get('Dead bug') == href('Dead bug'), links)
    ok('override: other exercises keep search links', links.get('Trap bar deadlift') is None and links.get('DB Romanian deadlift') == href('DB Romanian deadlift'), links)
    pg.locator('[data-start=Fri]').click(); pg.wait_for_timeout(300)
    log = dict(pg.locator('#exList .ex').evaluate_all("xs=>xs.map(x=>[x.querySelector('.name').textContent,x.querySelector('.ex-head a.vid').href])"))
    ok('log: started-from-plan exercises all have links, override kept', len(log) == 6 and log.get('Seated cable row') == VID and log.get("Farmer's carry") == href("Farmer's carry"), log)
    pg.reload(); pg.wait_for_function("window.__proplog.plan", timeout=8000)
    ok('log: override survives reload (kept in draft)', pg.locator('#exList .ex', has_text='Seated cable row').locator('a.vid').get_attribute('href') == VID)
    # hand-added exercises
    opts = pg.locator('#exPick option').evaluate_all("os=>os.map(o=>[o.value,o.textContent])")
    custom = [o[0] for o in opts if 'custom' in o[1].lower() or o[0] in ('__custom', 'custom')]
    pg.select_option('#exPick', custom[0]); pg.fill('#exCustom', 'Kettlebell swing & halo'); pg.click('#addEx'); pg.wait_for_timeout(200)
    h = pg.locator('#exList .ex', has_text='Kettlebell swing & halo').locator('a.vid').get_attribute('href')
    ok('log: hand-typed exercise gets an encoded search link', h == href('Kettlebell swing & halo'), h)
    pg.select_option('#exPick', custom[0]); pg.fill('#exCustom', 'seated cable row'); pg.click('#addEx'); pg.wait_for_timeout(200)
    hs = pg.locator('#exList .ex .ex-head a.vid').evaluate_all("as=>as.map(a=>a.href)")
    ok('log: hand-added exercise matching a plan exercise uses its video', hs[-1] == VID, hs[-3:])
    saved_before = pg.evaluate("localStorage.getItem('proplog.v1:neil')")
    ok('links do not change saved data format (draft only)', saved_before is None or '"video"' not in saved_before)
    ctx.close(); b.close()

print('\nRESULTS: %d/%d passed' % (sum(r for _, r in results), len(results)))
print('ERRORS:', errors or 'none')
sys.exit(0 if all(r for _, r in results) and not errors else 1)
