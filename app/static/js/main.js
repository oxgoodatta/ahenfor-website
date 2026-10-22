/* Public site interactions (progressive enhancement only). */
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* Mobile navigation */
  var toggle = document.querySelector("[data-nav-toggle]");
  if (toggle) {
    var closeNav = function () {
      document.body.classList.remove("nav-open");
      toggle.setAttribute("aria-expanded", "false");
    };
    toggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.body.classList.contains("nav-open")) { closeNav(); toggle.focus(); }
    });
    window.addEventListener("resize", function () { if (window.innerWidth >= 1100) closeNav(); });
  }

  /* Header background once the page scrolls past the hero top */
  var header = document.querySelector("[data-header]");
  if (header) {
    var onScroll = function () { header.classList.toggle("is-scrolled", window.scrollY > 24); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* Reveal on scroll */
  var revealables = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduceMotion) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { entry.target.classList.add("is-visible"); io.unobserve(entry.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    revealables.forEach(function (el) { io.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add("is-visible"); });
  }

  /* Hero video: only load on capable connections; muted, never with sound */
  var video = document.querySelector("[data-hero-video]");
  if (video) {
    var conn = navigator.connection || {};
    var saveData = conn.saveData || /(^|-)2g$/.test(conn.effectiveType || "");
    var button = document.querySelector("[data-video-toggle]");
    if (!reduceMotion && !saveData) {
      var source = document.createElement("source");
      source.src = video.getAttribute("data-src");
      source.type = video.getAttribute("data-type") || "video/mp4";
      video.appendChild(source);
      video.muted = true;
      video.load();
      var playPromise = video.play();
      if (playPromise && playPromise.catch) playPromise.catch(function () {});
      video.addEventListener("playing", function () { video.classList.add("is-playing"); });
      if (button) {
        button.hidden = false;
        var label = button.querySelector("[data-video-label]");
        button.addEventListener("click", function () {
          if (video.paused) { video.play(); button.classList.remove("is-paused"); label.textContent = "Pause"; button.setAttribute("aria-label", "Pause background video"); }
          else { video.pause(); button.classList.add("is-paused"); label.textContent = "Play"; button.setAttribute("aria-label", "Play background video"); }
        });
      }
    } else {
      video.remove();
    }
  }

  /* Auto-submit simple filter selects */
  document.querySelectorAll("form[data-autosubmit] select").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });

  /* Highlight the current phase in the project timeline navigation */
  var phaseNav = document.querySelector("[data-phase-nav]");
  if (phaseNav && "IntersectionObserver" in window) {
    var links = {};
    phaseNav.querySelectorAll("a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var phaseIo = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        Object.keys(links).forEach(function (k) { links[k].classList.remove("is-active"); });
        var link = links[entry.target.id];
        if (link) {
          link.classList.add("is-active");
          if (window.innerWidth < 1000) {
            var row = link.closest("ol");
            row.scrollTo({ left: link.offsetLeft - (row.clientWidth - link.offsetWidth) / 2, behavior: reduceMotion ? "auto" : "smooth" });
          }
        }
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    document.querySelectorAll("[data-phase]").forEach(function (el) { phaseIo.observe(el); });
  }
})();
