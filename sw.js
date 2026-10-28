// Prop Log service worker.
// - Page (navigations): network-first, cached copy offline. Only the app page itself is stored as
//   index.html; other pages (withings.html OAuth callback) are cached under their own URL.
// - Plans (plans/*.json): network-first with no HTTP cache, so coach updates show on next open;
//   offline falls back to the last cached copy (marked with an X-Proplog-Cache header).
// - config.js (cloud sync config): network-first, cached copy offline.
// - Everything else: cache-first app shell. Supabase API calls are cross-origin and never touched.
const CACHE = 'proplog-v7';
const ASSETS = ['./', './index.html', './manifest.json', './icon.svg', './icon-192.png', './icon-512.png'];
const OPTIONAL = ['./config.js', './plans/tom.json', './plans/nikki.json', './plans/elspeth.json', './withings.html'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(ASSETS).then(() => Promise.all(OPTIONAL.map(p => c.add(new Request(p, { cache: 'no-store' })).catch(() => {})))))
    .then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  if (/\/plans\/[^/]+\.json$/.test(url.pathname) || /\/config\.js$/.test(url.pathname)) {
    const key = new Request(url.origin + url.pathname);
    e.respondWith(fetch(e.request, { cache: 'no-store' }).then(r => {
      if (r.ok) { const c = r.clone(); e.waitUntil(caches.open(CACHE).then(x => x.put(key, c))); }
      return r;
    }).catch(() => caches.match(key).then(hit => hit
      ? hit.text().then(body => new Response(body, { status: 200, headers: { 'Content-Type': hit.headers.get('Content-Type') || 'application/json', 'X-Proplog-Cache': '1' } }))
      : new Response(/\.js$/.test(url.pathname) ? '' : '{"error":"offline"}', { status: 503, headers: { 'Content-Type': 'application/json' } }))));
    return;
  }
  if (e.request.mode === 'navigate') {
    const isApp = /\/(index\.html)?$/.test(url.pathname);
    const key = isApp ? './index.html' : new Request(url.origin + url.pathname);
    e.respondWith(fetch(e.request).then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(key, c)); } return r; })
      .catch(() => caches.match(key).then(hit => hit || caches.match('./index.html'))));
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
    if (r.ok) { const c = r.clone(); caches.open(CACHE).then(x => x.put(e.request, c)); }
    return r;
  })));
});
