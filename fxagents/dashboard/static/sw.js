/* FX-Agents home-screen app. The page is fetched fresh every time (network first) so an update is never hidden
   behind a cache; the last good copy and the icons are kept only for when the phone is offline. Live data
   (/api, /ws) is never cached. */
const CACHE = "fx-shell-v1";
const SHELL = ["./", "icon-192.png", "icon-512.png", "apple-touch-icon.png"];
self.addEventListener("install", e => { self.skipWaiting(); e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {})); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || /\/(api|ws|login|logout|webhook)\b/.test(u.pathname)) return;
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).then(r => { if (r.ok && r.headers.get("content-type")?.includes("text/html") && !r.redirected) { const c = r.clone(); caches.open(CACHE).then(x => x.put("./", c)); } return r; })
      .catch(() => caches.match("./").then(r => r || new Response("<h2 style='font-family:system-ui'>Offline</h2><p>FX-Agents needs a connection.</p>", {headers: {"content-type": "text/html"}}))));
    return;
  }
  if (/\.png$/.test(u.pathname)) e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
