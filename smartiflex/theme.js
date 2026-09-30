/* Read the effective per-user HA theme through same-origin ingress only.
 * Standalone/cross-origin windows fall back to the operating-system setting.
 * No credentials, messages or network requests are used for theme detection. */
(() => {
  const media = matchMedia('(prefers-color-scheme: dark)');
  function syncTheme() {
    let dark = media.matches;
    try {
      let host = window;
      for (let depth = 0; depth < 5 && host.parent !== host; depth++) {
        host = host.parent;
        const mode = host.document.querySelector('home-assistant')?.hass?.themes?.darkMode;
        if (typeof mode === 'boolean') { dark = mode; break; }
      }
    } catch { /* Cross-origin parent: use system preference. */ }
    const value = dark ? 'dark' : 'light';
    if (document.documentElement.dataset.theme !== value) document.documentElement.dataset.theme = value;
  }
  syncTheme();
  media.addEventListener('change', syncTheme);
  window.addEventListener('pageshow', syncTheme);
  // HA updates its reactive hass property without changing DOM attributes.
  setInterval(() => { if (!document.hidden) syncTheme(); }, 1000);
})();
