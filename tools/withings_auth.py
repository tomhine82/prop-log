#!/usr/bin/env python3
"""One-time Withings sign-in for Prop Log body-stats sync.

    python3 tools/withings_auth.py                 # start helper, print authorize URL, wait (10 min)
    python3 tools/withings_auth.py --timeout 300
    python3 tools/withings_auth.py --code CODE     # manual fallback: exchange a code right now

Flow: open the printed URL in the browser on this box and sign in to Withings. Withings redirects to
https://tomhine82.github.io/prop-log/withings.html?code=..&state=.., which immediately navigates to
http://127.0.0.1:8765/callback?.. where this helper exchanges the code (valid ~30 s) and saves tokens to
/home/box/.proplog/withings_tokens.json (600). Needs WITHINGS_CLIENT_ID / WITHINGS_CLIENT_SECRET in env.
Secrets and tokens are never printed.
"""
import argparse, html, http.server, os, secrets, sys, threading, time, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import withings_common as wc

PAGE = """<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prop Log · Withings</title><style>body{{margin:0;padding:24px 16px;background:#f4f5f7;color:#14171c;font:16px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}}
@media (prefers-color-scheme:dark){{body{{background:#0f1115;color:#eef1f5}}.c{{background:#181b21!important;border-color:#2c313a!important}}}}
.c{{max-width:520px;margin:0 auto;background:#fff;border:1px solid #dde1e6;border-radius:14px;padding:18px}}h1{{font-size:20px;margin:0 0 8px}}
.ok{{color:#1f9d55}}.bad{{color:#d64545}}</style></head><body><div class="c"><h1 class="{cls}">{title}</h1><p>{msg}</p></div></body></html>"""


def authorize_url(state):
    q = {'response_type': 'code', 'client_id': wc.env('WITHINGS_CLIENT_ID'), 'redirect_uri': wc.REDIRECT_URI,
         'scope': 'user.metrics', 'state': state}
    return wc.ACCOUNT + '/oauth2_user/authorize2?' + urllib.parse.urlencode(q)


def exchange(code):
    tok = wc.withings_token_request({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': wc.REDIRECT_URI})
    wc.write_json_atomic(wc.TOKENS, tok)
    return tok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--timeout', type=int, default=600, help='seconds to wait for the callback (default 600)')
    ap.add_argument('--code', help='exchange this authorization code immediately (manual fallback)')
    ap.add_argument('--url-file', default=os.path.join(wc.HOME, 'withings_authorize_url.txt'),
                    help='also write the authorize URL here (600)')
    ap.add_argument('--no-print-url', action='store_true', help='only write the URL to --url-file')
    a = ap.parse_args(argv)
    try:
        wc.env('WITHINGS_CLIENT_ID'); wc.env('WITHINGS_CLIENT_SECRET'); wc.ensure_home()
        if a.code:
            tok = exchange(a.code.strip())
            print(f'OK: Withings tokens saved to {wc.TOKENS} (Withings user {tok["userid"]}, scope {tok["scope"]}).')
            return 0
        return serve(a)
    except wc.Fail as e:
        print('ERROR: ' + str(e), file=sys.stderr); return e.code


def serve(a):
    state = secrets.token_urlsafe(24)
    result = {}
    done = threading.Event()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass   # never log query strings (they hold the code)
        def page(self, status, ok, title, msg):
            b = PAGE.format(cls='ok' if ok else 'bad', title=html.escape(title), msg=msg).encode()
            self.send_response(status); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(b)))
            self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            if u.path != '/callback':
                return self.page(404, False, 'Not found', 'This helper only handles /callback.')
            q = dict(urllib.parse.parse_qsl(u.query))
            if done.is_set():
                return self.page(200, 'ok' in result, 'Already handled', 'You can close this tab.')
            if not secrets.compare_digest(q.get('state', ''), state):
                print('Callback with wrong/missing state ignored (stale tab?).', file=sys.stderr)
                return self.page(400, False, 'State mismatch', 'This sign-in did not come from the running helper. Use the newest authorize URL.')
            if q.get('error'):
                result['err'] = wc.Fail('Withings returned error: ' + q['error'] + (' – ' + q['error_description'] if q.get('error_description') else ''), 1)
                done.set()
                return self.page(400, False, 'Withings sign-in failed', html.escape(str(result['err'])))
            if not q.get('code'):
                return self.page(400, False, 'No code', 'The callback had no authorization code.')
            try:
                tok = exchange(q['code'])
                result['ok'] = tok
                self.page(200, True, 'Withings connected ✓', 'Prop Log can now sync Tom\'s body stats. You can close this tab.')
            except wc.Fail as e:
                result['err'] = e
                self.page(500, False, 'Could not finish sign-in', html.escape(str(e)) + '<br>Codes expire after ~30 s – run the helper again.')
            done.set()

    try:
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.port), H)
    except OSError as e:
        raise wc.Fail(f'Cannot listen on 127.0.0.1:{a.port}: {e}', 1)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    url = authorize_url(state)
    wc.ensure_home()
    with open(os.open(a.url_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        f.write(url + '\n')
    os.chmod(a.url_file, 0o600)
    print(f'Listening on http://127.0.0.1:{a.port}/callback (timeout {a.timeout}s).')
    print(f'Authorize URL written to {a.url_file}')
    if not a.no_print_url:
        print('Open this URL in the browser on this box and sign in to Withings:\n\n' + url + '\n', flush=True)
    sys.stdout.flush()
    finished = done.wait(a.timeout)
    time.sleep(0.3)   # let the success page flush
    srv.shutdown(); srv.server_close()
    try: os.unlink(a.url_file)
    except FileNotFoundError: pass
    if not finished:
        raise wc.Fail(f'Timed out after {a.timeout}s waiting for the Withings callback.', 1)
    if 'err' in result:
        raise result['err']
    tok = result['ok']
    print(f'OK: Withings tokens saved to {wc.TOKENS} (Withings user {tok["userid"]}, scope {tok["scope"]}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
