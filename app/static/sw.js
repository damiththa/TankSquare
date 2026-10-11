/**
 * TankSquare Rural Offline Service Worker (`sw.js`)
 *
 * Pre-caches the Tanker Driver Mobile Browser View (`/driver`) and route API responses
 * so CDL fuel drivers can view property grids, what3words squares, and hose-reach paths
 * even in rural cell dead zones (0 bars).
 */

const CACHE_NAME = "tanksquare-offline-v1";
const STATIC_ASSETS = [
  "/",
  "/driver",
  "/static/widget.js",
  "/api/v1/driver/routes",
  "/api/v1/config/public",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((k) => {
          if (k !== CACHE_NAME) return caches.delete(k);
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((networkResp) => {
        const clone = networkResp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return networkResp;
      })
      .catch(() => caches.match(event.request))
  );
});
