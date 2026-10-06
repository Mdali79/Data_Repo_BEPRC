/* BEPRC Data Platform — UI behaviour (no external libraries).
 *
 *  - Theme toggle + mobile sidebar
 *  - Modals: BEPRC.confirm({...}) -> Promise<boolean>, BEPRC.alert({...})
 *  - data-confirm on any <form>, submit <button> or <a>: asks before acting
 *  - Django messages: with a title  -> acknowledgement modal
 *                     without title -> toast
 *  - Pagination helpers (rows per page, jump to page)
 *  - Date-range picker ([data-drp]) with presets, 2-month calendar
 */
(function () {
  "use strict";

  var ICONS = { info: "i-check", success: "i-check", error: "i-alert", warning: "i-alert", danger: "i-alert", question: "i-help" };
  function icon(id) { return '<svg class="icon"><use href="#' + id + '"/></svg>'; }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }

  /* ---------------- Theme & sidebar ---------------- */
  function initChrome() {
    var btn = document.getElementById("themeToggle");
    if (btn) btn.addEventListener("click", function () {
      var root = document.documentElement;
      var cur = root.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var next = cur === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("beprc-theme", next); } catch (e) {}
      document.dispatchEvent(new CustomEvent("themechange"));
    });
    var menu = document.querySelector(".menu-btn");
    if (menu) menu.addEventListener("click", function (e) { e.stopPropagation(); document.body.classList.toggle("nav-open"); });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar")) document.body.classList.remove("nav-open");
    });
  }

  /* ---------------- Modal ---------------- */
  var modalEl, modalQueue = [], modalBusy = false;

  function ensureModal() {
    if (modalEl) return modalEl;
    modalEl = document.createElement("div");
    modalEl.className = "modal-backdrop";
    modalEl.innerHTML =
      '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="mTitle">' +
      '<div class="modal-icon"></div><h3 id="mTitle"></h3><p></p>' +
      '<div class="modal-actions"><button type="button" class="btn btn-outline" data-m="cancel"></button>' +
      '<button type="button" class="btn" data-m="ok"></button></div></div>';
    document.body.appendChild(modalEl);
    return modalEl;
  }

  function openModal(o) {
    return new Promise(function (resolve) {
      modalQueue.push({ o: o, resolve: resolve });
      if (!modalBusy) nextModal();
    });
  }

  function nextModal() {
    var item = modalQueue.shift();
    if (!item) { modalBusy = false; return; }
    modalBusy = true;
    var o = item.o, el = ensureModal();
    var variant = o.variant || "info";
    var ic = el.querySelector(".modal-icon");
    ic.className = "modal-icon " + variant;
    ic.innerHTML = icon(o.icon || ICONS[variant] || "i-check");
    el.querySelector("h3").textContent = o.title || "";
    el.querySelector("p").textContent = o.message || "";
    var ok = el.querySelector('[data-m="ok"]'), cancel = el.querySelector('[data-m="cancel"]');
    ok.textContent = o.ok || "OK";
    ok.className = "btn" + (variant === "danger" ? " btn-danger" : "");
    cancel.textContent = o.cancel || "Cancel";
    cancel.style.display = o.alert ? "none" : "";
    var prevFocus = document.activeElement;

    function close(result) {
      el.classList.remove("open");
      ok.onclick = cancel.onclick = el.onclick = null;
      document.removeEventListener("keydown", onKey, true);
      if (prevFocus && prevFocus.focus) try { prevFocus.focus(); } catch (e) {}
      item.resolve(result);
      setTimeout(nextModal, 170);
    }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); close(!!o.alert); }
      else if (e.key === "Tab") { // keep focus inside the dialog
        var f = [cancel, ok].filter(function (b) { return b.style.display !== "none"; });
        var i = f.indexOf(document.activeElement);
        e.preventDefault();
        f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
    }
    ok.onclick = function () { close(true); };
    cancel.onclick = function () { close(false); };
    el.onclick = function (e) { if (e.target === el) close(!!o.alert); };
    document.addEventListener("keydown", onKey, true);
    requestAnimationFrame(function () { el.classList.add("open"); (o.alert ? ok : (variant === "danger" ? cancel : ok)).focus(); });
  }

  var BEPRC = window.BEPRC = {
    confirm: function (o) { return openModal(Object.assign({ variant: "info", ok: "Confirm" }, o)); },
    alert: function (o) { return openModal(Object.assign({ alert: true, ok: "OK" }, o)); },
    toast: toast,
  };

  /* ---------------- Toasts ---------------- */
  function toast(message, level) {
    var box = document.querySelector(".toasts");
    if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("aria-live", "polite"); document.body.appendChild(box); }
    var t = document.createElement("div");
    t.className = "toast " + (level || "info");
    t.innerHTML = icon(ICONS[level] || "i-check") + "<div>" + esc(message) + '</div><button class="x" aria-label="Dismiss">' + icon("i-x") + "</button>";
    box.appendChild(t);
    var kill = function () { t.style.transition = "opacity .2s"; t.style.opacity = "0"; setTimeout(function () { t.remove(); }, 200); };
    t.querySelector(".x").onclick = kill;
    setTimeout(kill, 5000);
  }

  function initFlash() {
    var holder = document.getElementById("flash");
    if (!holder) return;
    Array.prototype.forEach.call(holder.children, function (m) {
      var level = m.getAttribute("data-level") || "info", title = m.getAttribute("data-title");
      if (title) BEPRC.alert({ title: title, message: m.textContent.trim(), variant: level === "error" ? "error" : level, ok: "OK, got it" });
      else toast(m.textContent.trim(), level);
    });
  }

  /* ---------------- Confirm before acting ---------------- */
  function confirmOpts(src) {
    return {
      title: src.getAttribute("data-confirm-title") || "Are you sure?",
      message: src.getAttribute("data-confirm") || "",
      ok: src.getAttribute("data-confirm-ok") || "Confirm",
      variant: src.getAttribute("data-confirm-variant") || "question",
      icon: src.getAttribute("data-confirm-variant") === "danger" ? "i-trash" : "i-help",
    };
  }

  function initConfirm() {
    document.addEventListener("submit", function (e) {
      var form = e.target, btn = e.submitter;
      var src = btn && btn.hasAttribute("data-confirm") ? btn : (form.hasAttribute("data-confirm") ? form : null);
      if (!src) return;
      if (form.dataset.confirmed === "1") { form.dataset.confirmed = ""; return; }
      e.preventDefault();
      e.stopImmediatePropagation();
      BEPRC.confirm(confirmOpts(src)).then(function (ok) {
        if (!ok) return;
        form.dataset.confirmed = "1";
        if (form.requestSubmit) form.requestSubmit(btn || undefined); else form.submit();
      });
    }, true);

    document.addEventListener("click", function (e) {
      var a = e.target.closest("a[data-confirm]");
      if (!a) return;
      e.preventDefault();
      BEPRC.confirm(confirmOpts(a)).then(function (ok) { if (ok) location.href = a.href; });
    });

    // Loading state on any form that actually goes ahead.
    document.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      var btn = e.submitter;
      if (btn && btn.hasAttribute("data-loading")) {
        btn.classList.add("loading");
        var label = btn.getAttribute("data-loading");
        if (label) btn.innerHTML = '<span class="spinner"></span>' + esc(label);
      }
    });
  }

  /* ---------------- Pagination ---------------- */
  function setParams(changes) {
    var u = new URL(location.href);
    Object.keys(changes).forEach(function (k) {
      if (changes[k] == null || changes[k] === "") u.searchParams.delete(k); else u.searchParams.set(k, changes[k]);
    });
    location.href = u.toString();
  }
  function initPagination() {
    document.querySelectorAll("select[data-per-page]").forEach(function (s) {
      s.addEventListener("change", function () { setParams({ per_page: s.value, page: null }); });
    });
    document.querySelectorAll("form[data-page-jump]").forEach(function (f) {
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        var inp = f.querySelector("input"), max = +inp.max || 1, v = Math.min(max, Math.max(1, parseInt(inp.value, 10) || 1));
        setParams({ page: v });
      });
    });
    // Keep filter URLs clean: don't send empty fields.
    document.addEventListener("submit", function (e) {
      var f = e.target;
      if (e.defaultPrevented || !f.classList.contains("filters")) return;
      Array.prototype.forEach.call(f.elements, function (el) { if (el.name && !el.value) el.disabled = true; });
    });
    // Auto-submit filter selects/checkboxes marked data-autosubmit.
    document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
      el.addEventListener("change", function () { el.form && (el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit()); });
    });
  }

  /* ---------------- Date range picker ---------------- */
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  var DOW = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
  function iso(d) { return d ? d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") : ""; }
  function parse(s) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ""); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
  function fmt(d) { return d ? d.getDate() + " " + MONTHS[d.getMonth()].slice(0, 3) + " " + d.getFullYear() : ""; }
  function same(a, b) { return a && b && a.getTime() === b.getTime(); }
  function today() { var t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); }
  function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }

  function DateRange(root) {
    var inS = root.querySelector("[data-drp-start]"), inE = root.querySelector("[data-drp-end]");
    var trigger = root.querySelector(".drp-trigger"), label = root.querySelector(".drp-label"), pop = root.querySelector(".drp-pop");
    var start = parse(inS.value), end = parse(inE.value), hover = null;
    var view = start ? new Date(start.getFullYear(), start.getMonth(), 1) : new Date(today().getFullYear(), today().getMonth() - 1, 1);

    function render() {
      var t = today();
      var presets = [
        ["Today", t, t], ["Yesterday", addDays(t, -1), addDays(t, -1)],
        ["Last 7 days", addDays(t, -6), t], ["Last 30 days", addDays(t, -29), t],
        ["This month", new Date(t.getFullYear(), t.getMonth(), 1), t],
        ["Last month", new Date(t.getFullYear(), t.getMonth() - 1, 1), new Date(t.getFullYear(), t.getMonth(), 0)],
        ["This year", new Date(t.getFullYear(), 0, 1), t], ["All time", null, null],
      ];
      var h = '<div class="drp-presets">' + presets.map(function (p, i) { return '<button type="button" data-preset="' + i + '">' + p[0] + "</button>"; }).join("") + "</div>";
      h += '<div class="drp-main"><div class="drp-months">';
      for (var k = 0; k < 2; k++) {
        var m = new Date(view.getFullYear(), view.getMonth() + k, 1);
        h += '<div class="drp-month"><div class="drp-head">';
        h += k === 0 ? '<button type="button" class="drp-nav" data-nav="-1" aria-label="Previous month">' + icon("i-chev-left") + "</button>" : "<span style=\"width:30px\"></span>";
        if (k === 0) {
          h += '<span><select data-sel="m" aria-label="Month">' + MONTHS.map(function (n, i) { return "<option value=" + i + (i === m.getMonth() ? " selected" : "") + ">" + n + "</option>"; }).join("") + "</select>";
          var y0 = t.getFullYear() - 10, y1 = t.getFullYear() + 1, ys = "";
          for (var y = y1; y >= y0; y--) ys += "<option" + (y === m.getFullYear() ? " selected" : "") + ">" + y + "</option>";
          h += '<select data-sel="y" aria-label="Year">' + ys + "</select></span>";
        } else {
          h += '<strong style="font-size:13px">' + MONTHS[m.getMonth()] + " " + m.getFullYear() + "</strong>";
        }
        h += k === 1 ? '<button type="button" class="drp-nav" data-nav="1" aria-label="Next month">' + icon("i-chev-right") + "</button>" : "<span style=\"width:30px\"></span>";
        h += '</div><div class="drp-grid">' + DOW.map(function (d) { return '<div class="drp-dow">' + d + "</div>"; }).join("");
        var first = new Date(m.getFullYear(), m.getMonth(), 1 - m.getDay());
        var rangeEnd = end || (start && hover && hover > start ? hover : null);
        for (var i = 0; i < 42; i++) {
          var d = addDays(first, i), cls = "drp-day";
          if (d.getMonth() !== m.getMonth()) cls += " other";
          if (same(d, t)) cls += " today";
          if (start && same(d, start)) cls += " start";
          if (rangeEnd && same(d, rangeEnd)) cls += " end";
          if (start && !rangeEnd && same(d, start)) cls += " end";
          if (start && rangeEnd && d > start && d < rangeEnd) cls += " in-range";
          h += '<button type="button" class="' + cls + '" data-day="' + iso(d) + '"><span>' + d.getDate() + "</span></button>";
        }
        h += "</div></div>";
      }
      h += '</div><div class="drp-foot"><span class="sel">' + (start ? "<b>" + fmt(start) + "</b> – " + (end ? "<b>" + fmt(end) + "</b>" : "pick an end date") : "Pick a start date") + "</span>";
      h += '<button type="button" class="btn btn-ghost btn-sm" data-act="cancel">Cancel</button><button type="button" class="btn btn-sm" data-act="apply">Apply</button></div></div>';
      pop.innerHTML = h;
    }

    function updateLabel() {
      var s = parse(inS.value), e = parse(inE.value);
      if (s || e) {
        label.innerHTML = esc(s && e ? (same(s, e) ? fmt(s) : fmt(s) + " – " + fmt(e)) : (s ? "From " + fmt(s) : "Until " + fmt(e)));
        root.querySelector(".drp-clear").style.display = "";
      } else {
        label.innerHTML = '<span class="ph">' + esc(root.getAttribute("data-placeholder") || "Any date") + "</span>";
        root.querySelector(".drp-clear").style.display = "none";
      }
    }

    function commit() {
      if (start && !end) end = start;
      inS.value = iso(start); inE.value = iso(end);
      updateLabel(); close();
      var f = root.closest("form");
      if (f && root.hasAttribute("data-submit")) f.requestSubmit ? f.requestSubmit() : f.submit();
    }
    function open() {
      document.querySelectorAll(".drp.open").forEach(function (o) { if (o !== root) o.classList.remove("open"); });
      start = parse(inS.value); end = parse(inE.value);
      if (start) view = new Date(start.getFullYear(), start.getMonth(), 1);
      render(); root.classList.add("open");
      var r = pop.getBoundingClientRect();
      pop.style.left = ""; pop.style.right = "";
      if (r.right > window.innerWidth - 8) { pop.style.left = "auto"; pop.style.right = "0"; }
    }
    function close() { root.classList.remove("open"); }

    trigger.addEventListener("click", function (e) {
      if (e.target.closest(".drp-clear")) { start = end = null; commit(); return; }
      root.classList.contains("open") ? close() : open();
    });
    pop.addEventListener("click", function (e) {
      e.stopPropagation();
      var b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.nav) { view = new Date(view.getFullYear(), view.getMonth() + (+b.dataset.nav), 1); render(); }
      else if (b.dataset.day) {
        var d = parse(b.dataset.day);
        if (!start || end) { start = d; end = null; }
        else if (d < start) { start = d; }
        else { end = d; }
        render();
      }
      else if (b.dataset.preset) {
        var t = today(), p = +b.dataset.preset;
        var map = [[t, t], [addDays(t, -1), addDays(t, -1)], [addDays(t, -6), t], [addDays(t, -29), t],
          [new Date(t.getFullYear(), t.getMonth(), 1), t], [new Date(t.getFullYear(), t.getMonth() - 1, 1), new Date(t.getFullYear(), t.getMonth(), 0)],
          [new Date(t.getFullYear(), 0, 1), t], [null, null]][p];
        start = map[0]; end = map[1]; commit();
      }
      else if (b.dataset.act === "apply") commit();
      else if (b.dataset.act === "cancel") close();
    });
    pop.addEventListener("change", function (e) {
      var s = e.target.dataset.sel;
      if (s === "m") view = new Date(view.getFullYear(), +e.target.value, 1);
      if (s === "y") view = new Date(+e.target.value, view.getMonth(), 1);
      render();
    });
    pop.addEventListener("mouseover", function (e) {
      var b = e.target.closest("[data-day]");
      if (b && start && !end) { var d = parse(b.dataset.day); if (!same(d, hover)) { hover = d; render(); } }
    });
    document.addEventListener("click", function (e) { if (!root.contains(e.target)) close(); });
    root.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
    updateLabel();
  }

  function initDateRanges() { document.querySelectorAll("[data-drp]").forEach(DateRange); }

  /* ---------------- Boot ---------------- */
  // Re-enable filter fields disabled on submit when the page is restored from the back/forward cache.
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form.filters [disabled]").forEach(function (el) { el.disabled = false; });
  });

  function boot() { initChrome(); initConfirm(); initPagination(); initDateRanges(); initFlash(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
