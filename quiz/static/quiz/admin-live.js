/* Report real server outcomes even when HTMX replaces the submitting form. */
(function () {
  "use strict";
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    const element = event.detail && event.detail.elt;
    const form = element && element.closest && element.closest("form[hx-post]");
    if (!form || !form.getAttribute("action").includes("/admin-game/action/")) return;
    const xhr = event.detail.xhr;
    if (!xhr) return;
    xhr.addEventListener("loadend", function () {
      const notice = document.getElementById("admin-command-feedback");
      if (!notice) return;
      const accepted = xhr.status >= 200 && xhr.status < 300;
      notice.hidden = false;
      notice.setAttribute("role", accepted ? "status" : "alert");
      notice.className = accepted ? "gm-admin-feedback--success" : "gm-admin-feedback--error";
      notice.textContent = accepted
        ? "Opdracht door de server verwerkt."
        : "Opdracht geweigerd. Controleer de huidige spelstand en probeer opnieuw.";
    });
  });
}());
