/**
 * TankSquare Plaid-Style Multi-Vendor Browser Widget (`widget.js`)
 *
 * Usage on any Propane or Heating-Oil Provider's Customer Portal:
 * <script
 *   src="https://api.tanksquare.com/static/widget.js"
 *   data-vendor="gmp_vt"
 *   data-token="ts_tok_gmp_vt_demo1"
 *   data-button-text="Pin My Tank & Driveway (Free)"
 * ></script>
 *
 * Guarantees:
 * - 100% Browser-Based (No app download or software install)
 * - Zero Separate Account Creation for Residents
 * - 100% Free for Residents (B2B provider-paid)
 */
(function (window, document) {
  "use strict";

  const currentScript =
    document.currentScript ||
    document.querySelector('script[src*="widget.js"]');

  const scriptOrigin = currentScript && currentScript.src
    ? new URL(currentScript.src, window.location.href).origin
    : window.location.origin;

  const TankSquare = {
    version: "1.0.0",
    origin: scriptOrigin,

    /**
     * Open the TankSquare Resident Modal in the current browser window.
     */
    open: function (options) {
      const cfg = Object.assign(
        {
          vendorId: (currentScript && currentScript.getAttribute("data-vendor")) || "gmp_vt",
          token: (currentScript && currentScript.getAttribute("data-token")) || "ts_tok_gmp_vt_demo1",
          onComplete: null,
        },
        options || {}
      );

      const existing = document.getElementById("tanksquare-modal-backdrop");
      if (existing) existing.remove();

      const backdrop = document.createElement("div");
      backdrop.id = "tanksquare-modal-backdrop";
      backdrop.style.cssText =
        "position:fixed;inset:0;z-index:999999;background:rgba(15,23,42,0.75);" +
        "backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;";

      const container = document.createElement("div");
      container.style.cssText =
        "position:relative;width:100%;max-width:1180px;height:90vh;background:#0f172a;" +
        "border-radius:16px;overflow:hidden;box-shadow:0 25px 50px -12px rgba(0,0,0,0.6);" +
        "border:1px solid rgba(255,255,255,0.15);display:flex;flex-direction:column;";

      const closeBtn = document.createElement("button");
      closeBtn.innerHTML = "&times; Close TankSquare";
      closeBtn.style.cssText =
        "position:absolute;top:12px;right:16px;z-index:10;background:#1e293b;color:#f8fafc;" +
        "border:1px solid #475569;border-radius:8px;padding:6px 12px;font-family:sans-serif;" +
        "font-size:13px;font-weight:600;cursor:pointer;";
      closeBtn.onclick = function () {
        backdrop.remove();
      };

      const iframe = document.createElement("iframe");
      iframe.src =
        scriptOrigin +
        "/?vendor=" +
        encodeURIComponent(cfg.vendorId) +
        "&token=" +
        encodeURIComponent(cfg.token) +
        "&embedded=1";
      iframe.style.cssText = "width:100%;height:100%;border:0;flex:1;";
      iframe.allow = "geolocation; camera";

      container.appendChild(closeBtn);
      container.appendChild(iframe);
      backdrop.appendChild(container);
      document.body.appendChild(backdrop);

      window.addEventListener("message", function handler(ev) {
        if (ev.data && ev.data.type === "TANKSQUARE_PASS_SAVED") {
          if (typeof cfg.onComplete === "function") {
            cfg.onComplete(ev.data.payload);
          }
        }
      });
    },
  };

  window.TankSquare = TankSquare;

  // Auto-render launch button if `data-auto-button="true"` is set on the script tag
  if (currentScript && currentScript.getAttribute("data-auto-button") === "true") {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent =
      currentScript.getAttribute("data-button-text") ||
      "Pin My Tank & Driveway on TankSquare (Free)";
    btn.style.cssText =
      "background:#15803d;color:#ffffff;border:none;border-radius:10px;padding:12px 20px;" +
      "font-family:sans-serif;font-size:15px;font-weight:700;cursor:pointer;" +
      "box-shadow:0 4px 12px rgba(21,128,61,0.35);";
    btn.onclick = function () {
      TankSquare.open();
    };
    currentScript.parentNode.insertBefore(btn, currentScript.nextSibling);
  }
})(window, document);
