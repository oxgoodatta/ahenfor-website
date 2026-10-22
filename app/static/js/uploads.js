/* Progress update photo manager: multi-upload with per-file progress, captions,
   keyboard and drag reordering, and picking from the library.
   Without JavaScript the <input type=file multiple> simply posts with the form. */
(function () {
  "use strict";
  var admin = window.AhenforAdmin;
  var dropzone = document.querySelector("[data-dropzone]");
  if (!dropzone || !admin) return;

  var form = dropzone.closest("form");
  var input = dropzone.querySelector("[data-multi-file]");
  var queue = document.querySelector("[data-upload-queue]");
  var list = document.querySelector("[data-gallery-items]");
  var template = document.querySelector("[data-gallery-template]");
  var countEl = document.querySelector("[data-gallery-count]");
  var submit = form.querySelector("[data-submit]");
  var busyNote = form.querySelector("[data-upload-busy]");
  var pickBtn = dropzone.querySelector("[data-gallery-pick]");
  var maxPhotos = parseInt(dropzone.getAttribute("data-max"), 10) || 60;
  var active = 0;
  var pending = [];
  var CONCURRENCY = 2;

  function dirty() { form.dispatchEvent(new Event("ahenfor:dirty")); }

  function renumber() {
    var items = list.querySelectorAll("[data-gallery-item]");
    items.forEach(function (li, i) {
      li.querySelector("[data-pos]").textContent = i + 1;
      li.classList.toggle("cover", i === 0);
      li.querySelector('[data-move="-1"]').disabled = i === 0;
      li.querySelector('[data-move="1"]').disabled = i === items.length - 1;
    });
    countEl.textContent = items.length
      ? items.length + " photo" + (items.length === 1 ? "" : "s") + " in this update (maximum " + maxPhotos + "). Use ↑ ↓ or drag to change the order."
      : "No photos in this update yet.";
  }

  function existingIds() {
    return Array.prototype.map.call(list.querySelectorAll('input[name="media_id"]'), function (i) { return i.value; });
  }

  function addItem(asset) {
    if (existingIds().indexOf(String(asset.id)) !== -1) return;
    var li = template.content.firstElementChild.cloneNode(true);
    li.querySelector("img").src = asset.thumb_url;
    li.querySelector('input[name="media_id"]').value = asset.id;
    li.querySelector('input[name="media_caption"]').value = asset.caption || "";
    li.querySelector('input[name="media_alt"]').value = asset.alt_text || "";
    list.appendChild(li);
    renumber();
    dirty();
  }

  function setBusy() {
    var busy = active > 0 || pending.length > 0;
    submit.disabled = busy;
    busyNote.hidden = !busy;
  }

  function pump() {
    while (active < CONCURRENCY && pending.length) {
      var job = pending.shift();
      active += 1;
      run(job);
    }
    setBusy();
  }

  function run(job) {
    admin.uploadFile(job.file, "image", function (p) { job.bar.style.width = Math.round(p * 100) + "%"; })
      .then(function (asset) { addItem(asset); job.li.remove(); })
      .catch(function (err) {
        job.status.textContent = err.message;
        job.status.className = "err";
        job.bar.parentNode.hidden = true;
      })
      .then(function () { active -= 1; pump(); });
  }

  function enqueue(files) {
    var room = maxPhotos - list.querySelectorAll("[data-gallery-item]").length - pending.length - active;
    Array.prototype.slice.call(files).forEach(function (file, i) {
      var li = document.createElement("li");
      var name = document.createElement("span"); name.textContent = file.name;
      var status = document.createElement("span"); status.textContent = "Waiting…";
      var progress = document.createElement("div"); progress.className = "progress";
      var bar = document.createElement("span"); progress.appendChild(bar);
      li.appendChild(name); li.appendChild(status); li.appendChild(progress);
      queue.appendChild(li);
      if (i >= room) {
        status.textContent = "Not added: an update can hold at most " + maxPhotos + " photos.";
        status.className = "err"; progress.hidden = true;
        return;
      }
      if (!/^image\/(jpeg|png|webp)$/.test(file.type) && !/\.(jpe?g|png|webp)$/i.test(file.name)) {
        status.textContent = "Not a supported photo type (JPG, PNG or WebP)."; status.className = "err"; progress.hidden = true;
        return;
      }
      status.textContent = "Uploading…";
      pending.push({ file: file, li: li, bar: bar, status: status });
    });
    pump();
  }

  input.addEventListener("change", function () {
    if (input.files && input.files.length) enqueue(input.files);
    input.value = ""; /* uploaded separately; never re-sent with the form */
  });

  ["dragenter", "dragover"].forEach(function (type) {
    dropzone.addEventListener(type, function (e) {
      if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") !== -1) {
        e.preventDefault(); dropzone.classList.add("is-over");
      }
    });
  });
  ["dragleave", "drop"].forEach(function (type) {
    dropzone.addEventListener(type, function () { dropzone.classList.remove("is-over"); });
  });
  dropzone.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    enqueue(e.dataTransfer.files);
  });

  if (pickBtn) {
    pickBtn.hidden = false;
    pickBtn.addEventListener("click", function () {
      admin.openPicker("image", true, function (items) { items.forEach(addItem); });
    });
  }

  /* Reorder / remove with buttons (keyboard accessible) */
  list.addEventListener("click", function (e) {
    var li = e.target.closest("[data-gallery-item]");
    if (!li) return;
    var move = e.target.closest("[data-move]");
    if (move) {
      var dir = parseInt(move.getAttribute("data-move"), 10);
      var sibling = dir < 0 ? li.previousElementSibling : li.nextElementSibling;
      if (sibling) {
        list.insertBefore(li, dir < 0 ? sibling : sibling.nextElementSibling);
        renumber(); dirty();
        var same = li.querySelector('[data-move="' + dir + '"]');
        (same && !same.disabled ? same : move).focus();
      }
      return;
    }
    if (e.target.closest("[data-remove]")) {
      var next = li.nextElementSibling || li.previousElementSibling;
      li.remove(); renumber(); dirty();
      if (next) next.querySelector("[data-remove]").focus();
    }
  });

  /* Drag reordering */
  var dragging = null;
  list.addEventListener("dragstart", function (e) {
    var li = e.target.closest("[data-gallery-item]");
    if (!li || e.target.tagName === "INPUT") return;
    dragging = li; li.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", "photo");
  });
  list.addEventListener("dragend", function () {
    if (dragging) dragging.classList.remove("dragging");
    dragging = null; renumber();
  });
  list.addEventListener("dragover", function (e) {
    if (!dragging) return;
    e.preventDefault();
    var over = e.target.closest("[data-gallery-item]");
    if (!over || over === dragging) return;
    var rect = over.getBoundingClientRect();
    list.insertBefore(dragging, e.clientY > rect.top + rect.height / 2 ? over.nextSibling : over);
    dirty();
  });

  /* Keep the "you are adding to" banner in sync with the chosen phase */
  var banner = document.querySelector("[data-target-banner]");
  var phaseSelect = form.querySelector('select[name="phase_id"]');
  if (banner && phaseSelect) {
    var phases = {};
    try { phases = JSON.parse(banner.getAttribute("data-phases")); } catch (e) { phases = {}; }
    phaseSelect.addEventListener("change", function () {
      banner.querySelector("[data-target-phase]").textContent = phases[phaseSelect.value] || "";
    });
  }

  renumber();
})();
