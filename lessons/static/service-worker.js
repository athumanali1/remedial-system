const CACHE_NAME = 'remedial-system-v1';
const urlsToCache = [
  '/',
  '/staticfiles/css/dashboard.css',
  '/staticfiles/icons/apple-touch-icon.png',
  '/staticfiles/icons/favicon-96x96.png',
  '/staticfiles/icons/web-app-manifest-192x192.png',
  '/staticfiles/icons/web-app-manifest-512x512.png'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

self.addEventListener('fetch', function(e) {
  e.respondWith(
    caches.match(e.request)
      .then(function(response) {
        if (response) {
          return response;
        }
        return fetch(e.request);
      })
  );
});
