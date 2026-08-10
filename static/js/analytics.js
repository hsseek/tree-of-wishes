/* Visit + time-on-page beacons. The visit ping doubles as the bot filter:
   crawlers fetch the HTML but never run this script, so they aren't counted. */
(function () {
  var start = Date.now();
  var sent = false;

  /* One visit ping per page load. The server deduplicates to one visit per
     visitor per day and reads the referrer for traffic-source attribution. */
  function reportVisit() {
    if (!navigator.sendBeacon) return;
    var src = '';
    try {
      src = new URLSearchParams(window.location.search).get('src') || '';
    } catch (e) { /* older browser: fall back to referrer-only attribution */ }
    navigator.sendBeacon(
      '/api/track/visit'
        + '?path=' + encodeURIComponent(window.location.pathname)
        + '&ref=' + encodeURIComponent(document.referrer || '')
        + '&src=' + encodeURIComponent(src)
    );
  }
  reportVisit();

  function report() {
    if (sent) return;
    sent = true;
    var seconds = Math.round((Date.now() - start) / 1000);
    if (seconds <= 0) return;
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/track/dwell?s=' + seconds);
    }
  }

  // pagehide covers unload/navigation; visibilitychange covers tab switch and
  // mobile backgrounding (where pagehide is unreliable).
  window.addEventListener('pagehide', report);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') report();
  });
})();
