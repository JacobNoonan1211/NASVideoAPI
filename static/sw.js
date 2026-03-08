self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());

self.fetch = (event) => event.respondWith(fetch(event.request));