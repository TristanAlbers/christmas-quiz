/* Authenticated Game Master command feedback; server remains authoritative. */
(function () {
  "use strict";
  document.body.addEventListener("htmx:afterRequest", function (event) {
    const element = event.detail && event.detail.elt;
    const form = element && element.closest && element.closest("form[hx-post]");
    if (!form || !form.getAttribute("action").includes("/admin-game/action/")) return; // Ordinary 500 ms status polls are not command outcomes.
    const notice = document.getElementById("admin-command-feedback");
    if (!notice) return;
    const accepted = event.detail.successful;
    notice.hidden = false;
    notice.setAttribute("role", accepted ? "status" : "alert");
    notice.className = accepted ? "gm-admin-feedback--success" : "gm-admin-feedback--error";
    notice.textContent = accepted
      ? "Opdracht door de server verwerkt."
      : "Opdracht geweigerd. Controleer de huidige spelstand en probeer opnieuw.";
  });
}());
