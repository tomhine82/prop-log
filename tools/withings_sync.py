#!/usr/bin/env python3
"""Sync Tom's Withings body stats into Prop Log (Supabase public.proplog_data, kind 'bodyweight').

    python3 tools/withings_sync.py --dry-run     # show what would change (no Supabase writes, no state change)
    python3 tools/withings_sync.py               # sync since last run (first run: last 365 days)
    python3 tools/withings_sync.py --full        # ignore state, re-pull the last --days days (default 365)

Env: WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, SUPABASE_SERVICE_KEY (legacy service_role JWT or sb_secret_…),
optional SUPABASE_URL, PROPLOG_USER_ID, PROPLOG_TZ (default Europe/London), PROPLOG_HOME.
Files: $PROPLOG_HOME/withings_tokens.json (from withings_auth.py), withings_state.json (cursor + cached user_id).

One row per day: id = YYYY-MM-DD, data = {id,date,kg,updatedAt, fat_pct,fat_kg,muscle_kg,hydration_kg,bone_kg,
source:'withings', measured_at}. For each measure type the latest value of the day wins. updated_at is the time of
the latest Withings measurement of that day, so the app's newest-wins merge applies: an entry Tom typed or
deleted in the app after that weigh-in is left alone.

Exit codes: 0 ok · 1 error · 2 config missing · 3 Withings re-auth needed · 4 Supabase rejected the request.
No secrets or tokens are ever printed.
"""
import argparse, base64, datetime as dt, fcntl, json, math, os, sys, time, urllib.parse
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import withings_common as wc

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xvwugbmwdkyadfrefdhv.supabase.co').rstrip('/')
TABLE = 'proplog_data'
EMAIL = 'tomhine82@btinternet.com'
TYPES = {1: 'kg', 6: 'fat_pct', 8: 'fat_kg', 76: 'muscle_kg', 77: 'hydration_kg', 88: 'bone_kg'}
FIELDS = ['kg', 'fat_pct', 'fat_kg', 'muscle_kg', 'hydration_kg', 'bone_kg']
RANGES = {'kg': (30, 300), 'fat_pct': (1, 75), 'fat_kg': (0.5, 250), 'muscle_kg': (5, 200), 'hydration_kg': (5, 200), 'bone_kg': (0.5, 20)}
AMBIGUOUS_ATTRIB = {1}   # Withings: 1 = device could not tell which user stepped on the scale


def log(*a): print(*a, flush=True)


# ---------------- Withings ----------------
class Withings:
    def __init__(self):
        wc.env('WITHINGS_CLIENT_ID'); wc.env('WITHINGS_CLIENT_SECRET')
        self.tok = wc.read_json(wc.TOKENS)
        if not self.tok or not self.tok.get('refresh_token'):
            raise wc.Fail(f'No Withings tokens at {wc.TOKENS}. Run: python3 tools/withings_auth.py', 3)
        self.refreshed = False

    def refresh(self):
        try:
            new = wc.withings_token_request({'grant_type': 'refresh_token', 'refresh_token': self.tok['refresh_token']})
        except wc.Fail as e:
            raise wc.Fail(f'{e}. The Withings refresh token is expired or revoked – re-auth needed: '
                          'python3 tools/withings_auth.py', 3)
        new['userid'] = new.get('userid') or self.tok.get('userid', '')
        wc.write_json_atomic(wc.TOKENS, new)   # persist the rotated refresh token before anything else
        self.tok = new; self.refreshed = True

    def token(self):
        if int(self.tok.get('expires_at') or 0) - 300 <= time.time():
            self.refresh()
        return self.tok['access_token']

    def getmeas(self, **params):
        """All measure groups for the query (follows 'more'/'offset'). Returns (groups, body_meta)."""
        groups, meta, offset = [], {}, None
        for _ in range(200):
            p = {'action': 'getmeas', 'meastypes': ','.join(str(t) for t in TYPES), 'category': 1, **params}
            if offset: p['offset'] = offset
            for attempt in (0, 1):
                status, j = wc.http('POST', wc.API + '/measure', data=p, headers={'Authorization': 'Bearer ' + self.token()})
                st = j.get('status') if isinstance(j, dict) else None
                if st == 401 or status == 401:
                    if attempt == 0:
                        self.refresh(); continue
                    raise wc.Fail('Withings rejected the access token even after refresh – re-auth needed: python3 tools/withings_auth.py', 3)
                break
            if status != 200 or st != 0 or not isinstance(j.get('body'), dict):
                raise wc.Fail(f'Withings getmeas failed (HTTP {status}, status {st}: {j.get("error") if isinstance(j, dict) else ""})', 1)
            b = j['body']; meta = {k: b.get(k) for k in ('updatetime', 'timezone')}
            groups += b.get('measuregrps') or []
            if b.get('more') and b.get('offset'):
                offset = b['offset']
            else:
                break
        return groups, meta


def day_records(groups, tz):
    """Group measure groups by local day; per field the latest measurement of the day wins."""
    days = {}
    for g in sorted(groups, key=lambda g: (g.get('date') or 0, g.get('grpid') or 0)):
        if g.get('attrib') in AMBIGUOUS_ATTRIB or g.get('category', 1) != 1 or not g.get('date'):
            continue
        ts = int(g['date']); mod = max(ts, int(g.get('modified') or 0))
        day = dt.datetime.fromtimestamp(ts, tz).date().isoformat()
        d = days.setdefault(day, {'vals': {}, 'last': 0, 'measured': 0})
        for m in g.get('measures') or []:
            f = TYPES.get(m.get('type'))
            if not f: continue
            v = round(m['value'] * 10 ** m['unit'], 2)
            lo, hi = RANGES[f]
            if not (lo <= v <= hi) or not math.isfinite(v): continue
            d['vals'][f] = v   # later groups overwrite earlier ones
            d['measured'] = max(d['measured'], ts)
            d['last'] = max(d['last'], mod)
    out = {}
    for day, d in days.items():
        if 'kg' not in d['vals']:
            continue   # the app needs a weight; composition-only days are skipped
        out[day] = {'vals': d['vals'], 'ts_ms': d['last'] * 1000,
                    'measured_at': dt.datetime.fromtimestamp(d['measured'], tz).isoformat()}
    return out


def local_day_bounds(day, tz):
    d = dt.date.fromisoformat(day)
    start = dt.datetime.combine(d, dt.time(0), tz)
    return int(start.timestamp()), int((start + dt.timedelta(days=1)).timestamp()) - 1


# ---------------- Supabase ----------------
def key_kind(key):
    if key.startswith('sb_secret_'): return 'secret'
    if key.startswith('sb_publishable_'): return 'publishable'
    if key.count('.') == 2 and key.startswith('eyJ'):
        try:
            p = key.split('.')[1]; p += '=' * (-len(p) % 4)
            return 'jwt:' + str(json.loads(base64.urlsafe_b64decode(p)).get('role'))
        except Exception:
            return 'jwt:?'
    return 'unknown'


class Supa:
    def __init__(self, key):
        k = key_kind(key)
        if k not in ('secret', 'jwt:service_role'):
            raise wc.Fail(f'SUPABASE_SERVICE_KEY does not look like a secret/service_role key (detected: {k}). '
                          'Use the sb_secret_… key or the legacy service_role JWT.', 2)
        self.h = {'apikey': key}
        if k.startswith('jwt:'):
            self.h['Authorization'] = 'Bearer ' + key   # legacy JWT; sb_secret_ keys go on apikey only (not JWTs)

    def req(self, method, path, body=None, headers=None):
        h = dict(self.h); h.update(headers or {})
        status, j = wc.http(method, SUPABASE_URL + path, json_body=body, headers=h)
        if status >= 400:
            msg = (j.get('message') or j.get('msg') or j.get('error_description') or j.get('error')) if isinstance(j, dict) else str(j)[:200]
            code = j.get('code') if isinstance(j, dict) else None
            hint = ''
            if code == '42501' or 'permission denied' in str(msg).lower():
                hint = ' – the service role lacks table grants: run supabase/withings.sql in the SQL Editor'
            elif status in (401, 403):
                hint = ' – check SUPABASE_SERVICE_KEY'
            raise wc.Fail(f'Supabase {method} {path.split("?")[0]} failed: HTTP {status} {code or ""} {msg}{hint}', 4)
        return j

    def find_user(self, email):
        for page in range(1, 51):
            j = self.req('GET', f'/auth/v1/admin/users?page={page}&per_page=200')
            users = j.get('users', []) if isinstance(j, dict) else (j or [])
            hit = [u for u in users if (u.get('email') or '').lower() == email.lower()]
            if len(hit) == 1: return hit[0]['id']
            if len(users) < 200: break
        return None

    def user_from_rows(self, profile):
        rows = self.req('GET', f'/rest/v1/{TABLE}?select=user_id&profile=eq.{profile}&limit=1000')
        ids = {r['user_id'] for r in rows or []}
        return ids.pop() if len(ids) == 1 else None

    def existing(self, user_id, profile, days):
        if not days: return {}
        out, lo, hi = {}, min(days), max(days)
        for off in range(0, 100000, 1000):
            q = (f'/rest/v1/{TABLE}?select=id,data,updated_at,deleted&user_id=eq.{user_id}&profile=eq.{profile}'
                 f'&kind=eq.bodyweight&id=gte.{lo}&id=lte.{hi}&order=id.asc&limit=1000&offset={off}')
            rows = self.req('GET', q) or []
            for r in rows: out[r['id']] = r
            if len(rows) < 1000: break
        return out

    def upsert(self, rows):
        for i in range(0, len(rows), 200):
            self.req('POST', f'/rest/v1/{TABLE}?on_conflict=user_id,profile,kind,id', body=rows[i:i + 200],
                     headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})


def iso_ms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def parse_ts(s):
    return int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)


def plan(recs, existing):
    """Decide per day: insert / update / skip (with reason). Returns (writes, skipped{reason:[days]})."""
    writes, skipped = [], {}
    for day in sorted(recs):
        r = recs[day]; ex = existing.get(day); ts = r['ts_ms']
        data = {'id': 'wd-' + day, 'date': day, **{f: r['vals'][f] for f in FIELDS if f in r['vals']},
                'source': 'withings', 'measured_at': r['measured_at']}
        action = 'insert'
        if ex:
            ets = parse_ts(ex['updated_at']); ed = ex.get('data') or {}
            if ex.get('deleted'):
                if ts <= ets: skipped.setdefault('deleted in app', []).append(day); continue
            elif ed.get('source') == 'withings':
                if all(ed.get(f) == data.get(f) for f in FIELDS) and ed.get('measured_at') == data['measured_at']:
                    skipped.setdefault('unchanged', []).append(day); continue
                ts = max(ts, ets + 1)   # our own row: always replace with the fresh Withings values
            elif ts <= ets:
                skipped.setdefault('app entry is newer', []).append(day); continue
            if ed.get('id') and not ex.get('deleted'): data['id'] = ed['id']   # keep the app's record id
            action = 'update'
        data['updatedAt'] = ts
        writes.append((action, day, {'kind': 'bodyweight', 'id': day, 'data': data,
                                     'updated_at': iso_ms(ts), 'deleted': False}))
    return writes, skipped


def fmt_days(days, n=12):
    days = sorted(days)
    return ', '.join(days) if len(days) <= n else ', '.join(days[:n // 2]) + f', … ({len(days) - n} more) …, ' + ', '.join(days[-n // 2:])


def main(argv=None):
    ap = argparse.ArgumentParser(description='Sync Withings body stats into Prop Log.')
    ap.add_argument('--dry-run', action='store_true', help='print a summary, write nothing to Supabase or the state file')
    ap.add_argument('--full', action='store_true', help='ignore the saved cursor and re-pull the last --days days')
    ap.add_argument('--days', type=int, default=365, help='history window for the first/full run (default 365)')
    ap.add_argument('--profile', default='tom')
    ap.add_argument('--email', default=EMAIL)
    ap.add_argument('--user-id', default=os.environ.get('PROPLOG_USER_ID', ''))
    a = ap.parse_args(argv)
    try:
        wc.ensure_home()
        lockf = open(os.path.join(wc.HOME, '.withings_sync.lock'), 'w')
        try: fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise wc.Fail('Another withings_sync.py is already running', 1)
        return run(a)
    except wc.Fail as e:
        print('ERROR: ' + str(e), file=sys.stderr); return e.code


def run(a):
    tz = ZoneInfo(os.environ.get('PROPLOG_TZ', 'Europe/London'))
    state = wc.read_json(wc.STATE, {}) or {}
    started = int(time.time())
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()
    if not key and not a.dry_run:
        raise wc.Fail('SUPABASE_SERVICE_KEY is not set (needed to write to Supabase; --dry-run works without it)', 2)
    supa = Supa(key) if key else None
    w = Withings()

    # 1) Which days changed?
    cursor = None if a.full else state.get('lastupdate')
    if cursor:
        groups, meta = w.getmeas(lastupdate=int(cursor))
        days = sorted({dt.datetime.fromtimestamp(int(g['date']), tz).date().isoformat() for g in groups if g.get('date')})
        if days:   # re-read those whole days so "latest of the day" is computed over all of that day's measures
            lo, _ = local_day_bounds(days[0], tz); _, hi = local_day_bounds(days[-1], tz)
            full, _ = w.getmeas(startdate=lo, enddate=hi)
            groups = [g for g in full if dt.datetime.fromtimestamp(int(g['date']), tz).date().isoformat() in set(days)]
        mode = f'incremental since {dt.datetime.fromtimestamp(int(cursor), tz):%Y-%m-%d %H:%M %Z}'
    else:
        groups, meta = w.getmeas(startdate=started - a.days * 86400, enddate=started)
        mode = f'full, last {a.days} days'
    recs = day_records(groups, tz)
    log(f'Withings: {len(groups)} measure group(s), {len(recs)} day(s) with a weight ({mode})'
        + (' · access token refreshed' if w.refreshed else ''))
    if recs:
        log(f'  dates: {fmt_days(recs)}')
        last = recs[max(recs)]['vals']
        log('  latest ' + max(recs) + ': ' + ', '.join(f'{f} {last[f]}' for f in FIELDS if f in last))

    # 2) Who is Tom in Supabase?
    user_id = None
    if supa:
        user_id = a.user_id or (state.get('user_id') if state.get('user_email') == a.email.lower() else None)
        if not user_id:
            try:
                user_id = supa.find_user(a.email)
            except wc.Fail as e:
                log(f'  auth admin lookup failed ({e}); trying existing rows')
            user_id = user_id or supa.user_from_rows(a.profile)
            if not user_id:
                raise wc.Fail(f'Could not find the Supabase user for {a.email} (pass --user-id)', 4)
            state['user_id'] = user_id; state['user_email'] = a.email.lower()
        log(f'Supabase user: {user_id[:8]}… (profile {a.profile})')

    # 3) Compare with what's there and write.
    existing = supa.existing(user_id, a.profile, list(recs)) if supa else {}
    writes, skipped = plan(recs, existing)
    ins = [d for act, d, _ in writes if act == 'insert']; upd = [d for act, d, _ in writes if act == 'update']
    log(f'Plan: {len(ins)} insert, {len(upd)} update, {sum(len(v) for v in skipped.values())} skip'
        + ('' if supa else ' (no SUPABASE_SERVICE_KEY: existing rows not checked, all shown as inserts)'))
    for label, ds in (('insert', ins), ('update', upd)):
        if ds: log(f'  {label}: {fmt_days(ds)}')
    for why, ds in skipped.items():
        log(f'  skip ({why}): {fmt_days(ds)}')

    new_cursor = int(meta.get('updatetime') or started)
    if a.dry_run:
        log('Dry run: nothing written to Supabase; sync state unchanged.')
        if w.refreshed: log('  (rotated Withings tokens were saved)')
        return 0
    rows = [{'user_id': user_id, 'profile': a.profile, **r} for _, _, r in writes]
    if rows:
        supa.upsert(rows)
        after = supa.existing(user_id, a.profile, [d for _, d, _ in writes])
        lost = [r['id'] for r in rows if r['id'] not in after or parse_ts(after[r['id']]['updated_at']) != parse_ts(r['updated_at'])]
        if lost:
            log(f'  note: server kept a newer row for {len(lost)} day(s): {fmt_days(lost)}')
    state.update({'lastupdate': new_cursor, 'last_run': started, 'last_written': len(rows), 'profile': a.profile})
    wc.write_json_atomic(wc.STATE, state)
    log(f'OK: wrote {len(rows)} row(s) to {TABLE}; next sync from {dt.datetime.fromtimestamp(new_cursor, tz):%Y-%m-%d %H:%M %Z}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
