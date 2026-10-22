/* Admin dashboard enhancements. Every feature has a server-side equivalent;
   JavaScript only improves the experience (previews, progress, confirmation). */
(function () {
  "use strict";
  document.documentElement.classList.remove("no-js");

  var body = document.body;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  var limits = {};
  try { limits = JSON.parse(body.getAttribute("data-limits") || "{}"); } catch (e) { limits = {}; }

  function mb(bytes) { return Math.round(bytes / 1048576) + " MB"; }

  /* ------------------------------------------------------------------ */
  /* Upload helper (XHR so we get real progress events)                  */
  /* ------------------------------------------------------------------ */
  function uploadFile(file, profile, onProgress) {
    return new Promise(function (resolve, reject) {
      var limit = limits[profile];
      if (limit && file.size > limit) { reject(new Error(file.name + " is too large. Maximum size is " + mb(limit) + ".")); return; }
      var data = new FormData();
      data.append("file", file);
      data.append("profile", profile);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", body.getAttribute("data-upload-url"));
      xhr.setRequestHeader("X-CSRFToken", csrf);
      xhr.setRequestHeader("X-Requested-With", "fetch");
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.addEventListener("progress", function (e) { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); });
      xhr.onload = function () {
        var res = null;
        try { res = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
        if (xhr.status >= 200 && xhr.status < 300 && res && res.ok) resolve(res.asset);
        else if (xhr.status === 413) reject(new Error(file.name + " is larger than the server allows."));
        else reject(new Error((res && res.error) || "Upload failed (" + xhr.status + "). Please try again."));
      };
      xhr.onerror = function () { reject(new Error("Network error while uploading " + file.name + ". Check your connection and try again.")); };
      xhr.send(data);
    });
  }
  window.AhenforAdmin = { uploadFile: uploadFile };

  /* ------------------------------------------------------------------ */
  /* Layout: sidebar, dismissible alerts, auto-submitting filters         */
  /* ------------------------------------------------------------------ */
  var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = body.classList.toggle("sidebar-open");
      sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (body.classList.contains("sidebar-open") && !e.target.closest("#sidebar")) body.classList.remove("sidebar-open");
    });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-dismiss]");
    if (btn) btn.closest(".alert").remove();
  });
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  /* ------------------------------------------------------------------ */
  /* Confirmation dialog for destructive or publishing actions          */
  /* ------------------------------------------------------------------ */
  var confirmDialog = document.getElementById("confirm-dialog");
  function askConfirm(message, onYes) {
    if (!confirmDialog || typeof confirmDialog.showModal !== "function") { if (window.confirm(message)) onYes(); return; }
    confirmDialog.querySelector("[data-confirm-message]").textContent = message;
    var ok = confirmDialog.querySelector("[data-confirm-ok]");
    var cancel = confirmDialog.querySelector("[data-confirm-cancel]");
    function cleanup() { ok.removeEventListener("click", yes); cancel.removeEventListener("click", no); }
    function yes() { cleanup(); confirmDialog.close(); onYes(); }
    function no() { cleanup(); confirmDialog.close(); }
    ok.addEventListener("click", yes);
    cancel.addEventListener("click", no);
    confirmDialog.showModal();
    ok.focus();
  }
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.hasAttribute("data-confirm") || form.dataset.confirmed) return;
    e.preventDefault();
    askConfirm(form.getAttribute("data-confirm"), function () { form.dataset.confirmed = "1"; form.submit(); });
  });
  document.querySelectorAll("[data-confirm-button]").forEach(function (button) {
    button.addEventListener("click", function (e) {
      if (button.dataset.confirmed) return;
      e.preventDefault();
      askConfirm(button.getAttribute("data-confirm-button"), function () {
        button.dataset.confirmed = "1";
        if (button.form.requestSubmit) button.form.requestSubmit(button); else button.click();
      });
    });
  });

  /* ------------------------------------------------------------------ */
  /* Unsaved-change warning                                              */
  /* ------------------------------------------------------------------ */
  var dirtyForms = new Set();
  document.querySelectorAll("form[data-unsaved-warning]").forEach(function (form) {
    form.addEventListener("input", function () { dirtyForms.add(form); });
    form.addEventListener("change", function () { dirtyForms.add(form); });
    form.addEventListener("submit", function () { dirtyForms.delete(form); });
    form.addEventListener("ahenfor:dirty", function () { dirtyForms.add(form); });
  });
  window.addEventListener("beforeunload", function (e) {
    if (dirtyForms.size) { e.preventDefault(); e.returnValue = ""; }
  });

  /* ------------------------------------------------------------------ */
  /* Media library picker                                                */
  /* ------------------------------------------------------------------ */
  var picker = document.getElementById("media-picker");
  var pickerState = null;
  function renderPickerItems(items, append) {
    var grid = picker.querySelector("[data-picker-grid]");
    if (!append) grid.innerHTML = "";
    items.forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("aria-pressed", "false");
      btn.title = item.name;
      if (item.thumb_url && item.kind === "image") {
        var img = document.createElement("img");
        img.src = item.thumb_url; img.alt = item.alt_text || item.name; img.loading = "lazy";
        btn.appendChild(img);
      }
      var name = document.createElement("span");
      name.className = "name"; name.textContent = item.name;
      btn.appendChild(name);
      btn.addEventListener("click", function () {
        var selected = pickerState.selected;
        var idx = selected.findIndex(function (s) { return s.id === item.id; });
        if (!pickerState.multi) {
          grid.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
          pickerState.selected = idx >= 0 ? [] : [item];
          btn.setAttribute("aria-pressed", idx >= 0 ? "false" : "true");
        } else if (idx >= 0) { selected.splice(idx, 1); btn.setAttribute("aria-pressed", "false"); }
        else { selected.push(item); btn.setAttribute("aria-pressed", "true"); }
        picker.querySelector("[data-picker-count]").textContent = pickerState.selected.length ? pickerState.selected.length + " selected" : "";
      });
      grid.appendChild(btn);
    });
    picker.querySelector("[data-picker-empty]").hidden = grid.children.length > 0;
  }
  function loadPicker(append) {
    var url = new URL(body.getAttribute("data-library-url"), window.location.origin);
    url.searchParams.set("kind", pickerState.kind);
    url.searchParams.set("page", pickerState.page);
    if (pickerState.q) url.searchParams.set("q", pickerState.q);
    fetch(url, { headers: { "Accept": "application/json", "X-Requested-With": "fetch" }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderPickerItems(data.items || [], append);
        picker.querySelector("[data-picker-more]").hidden = !(data.pages && data.page < data.pages);
      })
      .catch(function () { picker.querySelector("[data-picker-empty]").hidden = false; });
  }
  function openPicker(kind, multi, onChoose) {
    if (!picker || typeof picker.showModal !== "function") return;
    pickerState = { kind: kind, multi: multi, onChoose: onChoose, selected: [], page: 1, q: "" };
    picker.querySelector("[data-picker-search]").value = "";
    picker.querySelector("[data-picker-count]").textContent = "";
    picker.querySelector("#picker-title").textContent = "Choose " + (multi ? kind + "s" : "a" + (kind === "image" ? "n " : " ") + kind) + " from the library";
    loadPicker(false);
    picker.showModal();
  }
  if (picker) {
    var searchTimer;
    picker.querySelector("[data-picker-search]").addEventListener("input", function (e) {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { pickerState.q = e.target.value.trim(); pickerState.page = 1; loadPicker(false); }, 300);
    });
    picker.querySelector("[data-picker-more]").addEventListener("click", function () { pickerState.page += 1; loadPicker(true); });
    picker.querySelectorAll("[data-picker-close]").forEach(function (b) { b.addEventListener("click", function () { picker.close(); }); });
    picker.querySelector("[data-picker-confirm]").addEventListener("click", function () {
      var chosen = pickerState.selected.slice();
      picker.close();
      if (chosen.length) pickerState.onChoose(chosen);
    });
  }
  window.AhenforAdmin.openPicker = openPicker;

  /* ------------------------------------------------------------------ */
  /* Single media fields (cover image, hero video, award PDF, ...)       */
  /* ------------------------------------------------------------------ */
  function setPreview(container, asset, kind) {
    container.innerHTML = "";
    if (!asset) { var s = document.createElement("span"); s.textContent = "No " + kind + " selected"; container.appendChild(s); return; }
    if (asset.kind === "image") { var img = document.createElement("img"); img.src = asset.thumb_url; img.alt = ""; container.appendChild(img); }
    else if (asset.kind === "video") { var v = document.createElement("video"); v.src = asset.url; v.muted = true; v.preload = "metadata"; container.appendChild(v); }
    else { var d = document.createElement("span"); d.className = "doc"; d.textContent = asset.name; container.appendChild(d); }
  }
  document.querySelectorAll("[data-media-field]").forEach(function (field) {
    var kind = field.getAttribute("data-kind");
    var profile = field.getAttribute("data-profile");
    var fileInput = field.querySelector("[data-file]");
    var idInput = field.querySelector("[data-id]");
    var preview = field.querySelector("[data-preview]");
    var clearBtn = field.querySelector("[data-clear]");
    var pickBtn = field.querySelector("[data-pick]");
    var progress = field.querySelector("[data-progress]");
    var bar = progress.querySelector("span");
    var status = field.querySelector("[data-status]");
    var form = field.closest("form");
    var submit = form ? form.querySelector('button[type="submit"]:not([name])') || form.querySelector('button[type="submit"]') : null;

    function changed() { if (form) form.dispatchEvent(new Event("ahenfor:dirty")); }
    if (pickBtn) {
      pickBtn.hidden = false;
      pickBtn.addEventListener("click", function () {
        openPicker(kind, false, function (items) {
          idInput.value = items[0].id; setPreview(preview, items[0], kind); clearBtn.hidden = false;
          status.textContent = "Selected from library: " + items[0].name; status.classList.remove("error"); changed();
        });
      });
    }
    clearBtn.addEventListener("click", function () {
      idInput.value = ""; fileInput.value = ""; setPreview(preview, null, kind); clearBtn.hidden = true;
      status.textContent = "Removed. Save the form to apply."; status.classList.remove("error"); changed();
    });
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      status.textContent = "Uploading " + file.name + "…"; status.classList.remove("error");
      progress.hidden = false; bar.style.width = "0%";
      if (submit) submit.disabled = true;
      uploadFile(file, profile, function (p) { bar.style.width = Math.round(p * 100) + "%"; })
        .then(function (asset) {
          idInput.value = asset.id; setPreview(preview, asset, kind); clearBtn.hidden = false;
          status.textContent = "Uploaded " + asset.name + ". Save the form to apply."; changed();
        })
        .catch(function (err) { status.textContent = err.message; status.classList.add("error"); })
        .then(function () {
          fileInput.value = ""; /* already uploaded: don't send the file again with the form */
          progress.hidden = true;
          if (submit) submit.disabled = false;
        });
    });
  });

  /* ------------------------------------------------------------------ */
  /* Hero form: show only the fields for the chosen background type      */
  /* ------------------------------------------------------------------ */
  var heroRadios = document.querySelectorAll('input[name="media_type"]');
  if (heroRadios.length && document.querySelector("[data-hero-for]")) {
    var syncHero = function () {
      var chosen = document.querySelector('input[name="media_type"]:checked');
      var type = chosen ? chosen.value : "image";
      document.querySelectorAll("[data-hero-for]").forEach(function (group) {
        group.hidden = group.getAttribute("data-hero-for") !== type;
      });
    };
    heroRadios.forEach(function (r) { r.addEventListener("change", syncHero); });
    syncHero();
  }

  /* ------------------------------------------------------------------ */
  /* Drag-and-drop phase ordering (arrow buttons work without this)      */
  /* ------------------------------------------------------------------ */
  var phaseList = document.querySelector("[data-phase-list]");
  var orderForm = document.querySelector("[data-phase-order-form]");
  if (phaseList && orderForm) {
    var dragged = null;
    phaseList.querySelectorAll("[data-drag-handle]").forEach(function (handle) {
      var card = handle.closest("[data-phase-id]");
      handle.addEventListener("dragstart", function (e) {
        dragged = card; card.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", card.getAttribute("data-phase-id"));
        try { e.dataTransfer.setDragImage(card, 20, 20); } catch (err) { /* ignore */ }
      });
      handle.addEventListener("dragend", function () {
        card.classList.remove("dragging"); dragged = null;
        phaseList.querySelectorAll(".drop-target").forEach(function (c) { c.classList.remove("drop-target"); });
      });
    });
    phaseList.addEventListener("dragover", function (e) {
      if (!dragged) return;
      e.preventDefault();
      var over = e.target.closest("[data-phase-id]");
      if (!over || over === dragged) return;
      var rect = over.getBoundingClientRect();
      var after = e.clientY > rect.top + rect.height / 2;
      phaseList.insertBefore(dragged, after ? over.nextSibling : over);
    });
    phaseList.addEventListener("drop", function (e) {
      if (!dragged) return;
      e.preventDefault();
      var ids = Array.prototype.map.call(phaseList.querySelectorAll("[data-phase-id]"), function (c, i) {
        var num = c.querySelector(".phase-num"); if (num) num.textContent = i + 1;
        return c.getAttribute("data-phase-id");
      });
      orderForm.querySelector("[data-phase-order]").value = ids.join(",");
      orderForm.hidden = false;
      orderForm.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }
})();
