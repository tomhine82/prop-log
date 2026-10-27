#!/usr/bin/env python3
"""Set (or create) a Prop Log sign-in password for a Supabase user – no email needed.

    NEW_PASSWORD='…' python3 tools/set_password.py --email tomhine82@btinternet.com
    python3 tools/set_password.py --email nikki@example.com --password-env NIKKI_PASSWORD

Uses SUPABASE_SERVICE_KEY (sb_secret_… on the apikey header only; legacy service_role JWT on apikey +
Authorization). Finds the user via the auth admin API and sets the password with email_confirm=true
(which also activates an unconfirmed account), or creates the user if missing.
Prints only 'updated'/'created' and the first 8 characters of the user id. Never prints the password or key.
Exit codes: 0 ok · 1 error · 2 config/input missing · 4 Supabase rejected the request.
"""
import argparse, base64, json, os, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import withings_common as wc   # shared HTTP helper + Fail (no Withings secrets needed)

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://xvwugbmwdkyadfrefdhv.supabase.co').rstrip('/')


def key_headers(key):
    if key.startswith('sb_secret_'):
        return {'apikey': key}
    if key.count('.') == 2 and key.startswith('eyJ'):
        try:
            p = key.split('.')[1]; p += '=' * (-len(p) % 4)
            role = json.loads(base64.urlsafe_b64decode(p)).get('role')
        except Exception:
            role = None
        if role == 'service_role':
            return {'apikey': key, 'Authorization': 'Bearer ' + key}
    raise wc.Fail('SUPABASE_SERVICE_KEY does not look like a secret (sb_secret_…) or service_role key', 2)


def req(h, method, path, body=None):
    status, j = wc.http(method, SUPABASE_URL + path, json_body=body, headers=h)
    if status >= 400:
        msg = (j.get('msg') or j.get('message') or j.get('error_description') or j.get('error')) if isinstance(j, dict) else str(j)[:200]
        code = (j.get('error_code') or j.get('code')) if isinstance(j, dict) else ''
        raise wc.Fail(f'Supabase {method} /auth/v1/admin/users failed: HTTP {status} {code or ""} {msg}'.rstrip(), 4)
    return j


def find_user(h, email):
    for page in range(1, 101):
        j = req(h, 'GET', f'/auth/v1/admin/users?page={page}&per_page=200')
        users = j.get('users', []) if isinstance(j, dict) else (j or [])
        hit = [u for u in users if (u.get('email') or '').lower() == email]
        if hit: return hit[0]
        if len(users) < 200: return None
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description='Set or create a Supabase email+password user for Prop Log.')
    ap.add_argument('--email', required=True)
    ap.add_argument('--password-env', default='NEW_PASSWORD', help='name of the env var holding the password (default NEW_PASSWORD)')
    a = ap.parse_args(argv)
    try:
        email = a.email.strip().lower()
        if '@' not in email or ' ' in email: raise wc.Fail('--email does not look like an email address', 2)
        pw = os.environ.get(a.password_env, '')
        if not pw: raise wc.Fail(f'{a.password_env} is not set in the environment', 2)
        if len(pw) < 8: raise wc.Fail(f'The password in {a.password_env} is shorter than 8 characters (the app requires 8+)', 2)
        h = key_headers(wc.env('SUPABASE_SERVICE_KEY'))
        u = find_user(h, email)
        if u:
            j = req(h, 'PUT', '/auth/v1/admin/users/' + urllib.parse.quote(u['id']), {'password': pw, 'email_confirm': True})
            print(f'updated {str((j or {}).get("id") or u["id"])[:8]}')
        else:
            j = req(h, 'POST', '/auth/v1/admin/users', {'email': email, 'password': pw, 'email_confirm': True})
            if not isinstance(j, dict) or not j.get('id'): raise wc.Fail('Supabase did not return the new user id', 4)
            print(f'created {j["id"][:8]}')
        return 0
    except wc.Fail as e:
        print('ERROR: ' + str(e), file=sys.stderr); return e.code


if __name__ == '__main__':
    sys.exit(main())
