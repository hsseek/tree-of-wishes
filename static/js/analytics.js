/* Time-on-page beacon. Sends one sample (seconds on page) when the page is
   hidden or unloaded. Resource-light: no heartbeats, fires at most once. */
(function () {
  var start = Date.now();
  var sent = false;

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
