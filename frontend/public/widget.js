/*
 * Policy Compass website widget (US-030).
 *
 * Add to any page:
 *   <script src="https://YOUR-POLICY-COMPASS/widget.js" data-organisation="your-slug" async></script>
 * Optional: data-colour="#1f5aa6", data-label="Ask a question", data-position="left".
 *
 * It adds a button that opens the organisation's public Policy Compass page in a panel. The panel
 * is the public page itself, so it uses exactly the same public-only answers and help routes.
 * No cookies, tracking or data from the host page are read or sent.
 */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || window.__policyCompassWidget) return;
  window.__policyCompassWidget = true;

  var slug = (script.getAttribute("data-organisation") || "").toLowerCase();
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(slug)) return;

  var origin = new URL(script.src, window.location.href).origin;
  var colour = script.getAttribute("data-colour") || "";
  if (!/^#[0-9a-fA-F]{6}$/.test(colour)) colour = "#1f5aa6";
  var label = (script.getAttribute("data-label") || "Ask a question").slice(0, 40);
  var side = script.getAttribute("data-position") === "left" ? "left" : "right";

  // Readable text on the brand colour (WCAG relative luminance).
  function luminance(hex) {
    var rgb = [1, 3, 5].map(function (i) {
      var c = parseInt(hex.substr(i, 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
  }
  var text = luminance(colour) > 0.179 ? "#141b24" : "#ffffff";

  var style = document.createElement("style");
  style.textContent =
    ".pcw-button{position:fixed;bottom:20px;" + side + ":20px;z-index:2147483000;display:inline-flex;" +
    "align-items:center;gap:8px;min-height:48px;padding:12px 20px;border:0;border-radius:999px;" +
    "background:" + colour + ";color:" + text + ";font:600 15px/1.2 system-ui,-apple-system,'Segoe UI',sans-serif;" +
    "box-shadow:0 6px 20px rgba(16,24,40,.25);cursor:pointer}" +
    ".pcw-button:focus-visible{outline:3px solid #2563eb;outline-offset:3px}" +
    ".pcw-panel{position:fixed;bottom:84px;" + side + ":20px;z-index:2147483000;width:min(400px,calc(100vw - 32px));" +
    "height:min(640px,calc(100vh - 120px));display:flex;flex-direction:column;background:#fff;border-radius:14px;" +
    "box-shadow:0 12px 40px rgba(16,24,40,.3);overflow:hidden}" +
    ".pcw-panel[hidden]{display:none}" +
    ".pcw-bar{display:flex;justify-content:flex-end;padding:4px;background:" + colour + "}" +
    ".pcw-close{min-width:40px;min-height:40px;border:0;border-radius:8px;background:transparent;color:" + text + ";" +
    "font:600 22px/1 system-ui,sans-serif;cursor:pointer}" +
    ".pcw-close:focus-visible{outline:3px solid #2563eb;outline-offset:-3px}" +
    ".pcw-frame{flex:1;width:100%;border:0}" +
    "@media (max-width:480px){.pcw-panel{inset:0;width:100%;height:100%;border-radius:0}}";
  document.head.appendChild(style);

  var button = document.createElement("button");
  button.type = "button";
  button.className = "pcw-button";
  button.textContent = label;
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", "pcw-panel");

  var panel = document.createElement("div");
  panel.id = "pcw-panel";
  panel.className = "pcw-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", label);
  panel.hidden = true;

  var bar = document.createElement("div");
  bar.className = "pcw-bar";
  var close = document.createElement("button");
  close.type = "button";
  close.className = "pcw-close";
  close.setAttribute("aria-label", "Close");
  close.textContent = "×";
  bar.appendChild(close);
  panel.appendChild(bar);

  var frame = null;
  function open() {
    if (!frame) {
      // Loaded on first open, so pages that never use the widget make no requests.
      frame = document.createElement("iframe");
      frame.className = "pcw-frame";
      frame.title = label;
      frame.src = origin + "/p/" + encodeURIComponent(slug) + "/widget";
      frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      panel.appendChild(frame);
    }
    panel.hidden = false;
    button.setAttribute("aria-expanded", "true");
    frame.focus();
  }
  function hide() {
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.focus();
  }

  button.addEventListener("click", function () {
    panel.hidden ? open() : hide();
  });
  close.addEventListener("click", hide);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) hide();
  });

  function mount() {
    document.body.appendChild(panel);
    document.body.appendChild(button);
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
