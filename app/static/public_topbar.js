(function () {
  function ready(fn){
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(() => {
    const path = window.location.pathname.replace(/\/$/, "");

    function markActive(selector) {
      document.querySelectorAll(selector).forEach(a => {
        const href = (a.getAttribute("href") || "").replace(/\/$/, "");
        if (href && (path === href || path.startsWith(href + "/"))) {
          a.classList.add("is-active");
        }
      });
    }

    markActive(".gm-topnav .gm-topnav-link");
    markActive("#gmMobileMenu .gm-mobile-link");

    const btn = document.querySelector(".gm-burger");
    const menu = document.getElementById("gmMobileMenu");
    const overlay = document.getElementById("gmMobileOverlay");

    if (!btn || !menu || !overlay) return;

    function openMenu(){
      menu.classList.add("is-open");
      overlay.classList.add("is-open");
      document.body.classList.add("is-menu-open");
      btn.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
    }

    function closeMenu(){
      menu.classList.remove("is-open");
      overlay.classList.remove("is-open");
      document.body.classList.remove("is-menu-open");
      btn.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    }

    btn.addEventListener("click", () => {
      overlay.classList.contains("is-open") ? closeMenu() : openMenu();
    });

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeMenu();
    });

    menu.querySelectorAll("a").forEach(a => a.addEventListener("click", closeMenu));

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeMenu();
    });
  });
})();
