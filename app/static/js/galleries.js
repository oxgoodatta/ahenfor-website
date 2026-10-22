/* Accessible photo lightbox. Links keep working (open the full image) without JavaScript. */
(function () {
  "use strict";
  var dialog = document.querySelector("[data-lightbox-dialog]");
  if (!dialog || typeof dialog.showModal !== "function") return;

  var imgEl = dialog.querySelector("[data-lightbox-img]");
  var captionEl = dialog.querySelector("[data-lightbox-caption]");
  var countEl = dialog.querySelector("[data-lightbox-count]");
  var items = [];
  var index = 0;
  var opener = null;

  function show(i) {
    index = (i + items.length) % items.length;
    var link = items[index];
    var thumb = link.querySelector("img");
    imgEl.src = link.getAttribute("href");
    imgEl.alt = thumb ? thumb.alt : "";
    captionEl.textContent = link.getAttribute("data-caption") || (thumb ? thumb.alt : "");
    countEl.textContent = (index + 1) + " / " + items.length;
    dialog.querySelector("[data-lightbox-prev]").hidden = items.length < 2;
    dialog.querySelector("[data-lightbox-next]").hidden = items.length < 2;
  }

  document.addEventListener("click", function (e) {
    var link = e.target.closest("a[data-lightbox]");
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    var group = link.closest("[data-gallery]");
    items = Array.prototype.slice.call((group || document).querySelectorAll("a[data-lightbox]"));
    opener = link;
    show(items.indexOf(link));
    dialog.showModal();
  });

  dialog.querySelector("[data-lightbox-close]").addEventListener("click", function () { dialog.close(); });
  dialog.querySelector("[data-lightbox-prev]").addEventListener("click", function () { show(index - 1); });
  dialog.querySelector("[data-lightbox-next]").addEventListener("click", function () { show(index + 1); });
  dialog.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") show(index - 1);
    if (e.key === "ArrowRight") show(index + 1);
  });
  dialog.addEventListener("click", function (e) { if (e.target === dialog || e.target.classList.contains("lightbox-stage")) dialog.close(); });
  dialog.addEventListener("close", function () { imgEl.removeAttribute("src"); if (opener) opener.focus(); });

  /* Basic swipe support */
  var startX = null;
  dialog.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; }, { passive: true });
  dialog.addEventListener("touchend", function (e) {
    if (startX === null) return;
    var dx = e.changedTouches[0].clientX - startX;
    if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
    startX = null;
  });
})();
