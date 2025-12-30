(function () {
  function absUrl(u){
    try { return new URL(u, window.location.origin).toString(); }
    catch { return window.location.href; }
  }

  async function doShare(btn){
    const title = btn.dataset.shareTitle || document.title;
    const text  = btn.dataset.shareText || "";
    const url   = absUrl(btn.dataset.shareUrl || window.location.href);

    // Share nativo (WhatsApp, etc.)
    if (navigator.share) {
      try { await navigator.share({ title, text, url }); } catch (_) {}
      return;
    }

    // Fallback: copiar
    if (navigator.clipboard?.writeText) {
      try{
        await navigator.clipboard.writeText(url);
        const old = btn.textContent;
        btn.textContent = "Copiado ✅";
        setTimeout(()=> btn.textContent = old, 1200);
      } catch (_) {}
    } else {
      window.prompt("Copia este enlace:", url);
    }
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".news-share");
    if (!btn) return;

    // IMPORTANTE: que no active el link de la card
    e.preventDefault();
    e.stopPropagation();

    doShare(btn);
  });
})();
