const CACHE_NAME = "wechat-card-v1";
const urlsToCache = [
  "/",
  "/css/style.css",
  "/js/config.js",
  "/js/vcard.js",
  "/js/wechat-jssdk.js",
  "/js/main-dynamic.js",
  "/favicon-192.png",
  "/favicon-512.png",
  "/manifest.json"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
