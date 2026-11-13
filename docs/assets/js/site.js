/* MedRadar site — navigation only.
   File: docs/assets/js/site.js  (loaded with `defer`)
   Budget: well under 6 KB. No framework, no external request.
   Progressive enhancement: the markup ships the navigation visible and
   `aria-expanded="true"`, so a reader without JavaScript keeps a usable menu.
   This script collapses it into the toggle only when the viewport is narrow. */
(function () {
  "use strict";

  var header = document.querySelector(".site-header");
  var toggle = header ? header.querySelector(".nav-toggle") : null;
  if (!header || !toggle) return;

  var narrow = window.matchMedia("(max-width: 900px)");

  function setOpen(open) {
    header.classList.toggle("is-collapsed", !open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function sync() {
    if (narrow.matches) {
      setOpen(false);
    } else {
      header.classList.remove("is-collapsed");
      toggle.setAttribute("aria-expanded", "false");
    }
  }

  toggle.addEventListener("click", function () {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      toggle.focus();
    }
  });

  if (typeof narrow.addEventListener === "function") {
    narrow.addEventListener("change", sync);
  } else if (typeof narrow.addListener === "function") {
    /* Safari < 14 */
    narrow.addListener(sync);
  }

  sync();
})();
