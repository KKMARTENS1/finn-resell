// Golflager – litt hjelp i nettleseren. Alt fungerer også uten.
(function () {
  "use strict";

  // Nedtrekkslister som filtrerer med én gang
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () { select.form.submit(); });
  });

  // Spør før sletting
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
    });
  });
  document.querySelectorAll("button[form]").forEach(function (button) {
    var target = document.getElementById(button.getAttribute("form"));
    if (!target || !target.hasAttribute("data-confirm")) return;
    button.addEventListener("click", function (event) {
      event.preventDefault();
      if (window.confirm(target.getAttribute("data-confirm"))) target.submit();
    });
  });

  // Knapper som tar litt tid (oppdatering): vis at noe skjer
  document.querySelectorAll("form[data-busy]").forEach(function (form) {
    form.addEventListener("submit", function () {
      document.querySelectorAll("button").forEach(function (button) {
        if (button.form !== form) return;
        button.disabled = true;
        button.textContent = form.getAttribute("data-busy");
      });
    });
  });

  // «Kopier teksten»-knapper
  document.querySelectorAll("button[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      var field = document.querySelector(button.getAttribute("data-copy"));
      if (!field) return;
      var done = function () { button.textContent = "Kopiert!"; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(field.value).then(done, function () {
          field.select(); document.execCommand("copy"); done();
        });
      } else {
        field.select(); document.execCommand("copy"); done();
      }
    });
  });

  // Verktøytips på grafene
  var tip = document.getElementById("tooltip");
  function showTip(el) {
    var value = el.getAttribute("data-tip-value");
    if (!tip || !value) return;
    tip.textContent = "";
    var strong = document.createElement("strong");
    strong.textContent = value;
    var label = document.createElement("span");
    label.textContent = el.getAttribute("data-tip-label") || "";
    tip.appendChild(strong);
    tip.appendChild(label);
    tip.hidden = false;
    var rect = el.getBoundingClientRect();
    var box = tip.getBoundingClientRect();
    var left = Math.min(window.innerWidth - box.width - 8, Math.max(8, rect.left + rect.width / 2 - box.width / 2));
    var top = rect.top - box.height - 8;
    if (top < 8) top = rect.bottom + 8;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }
  document.querySelectorAll("[data-tip-value]").forEach(function (el) {
    el.addEventListener("pointerenter", function () { showTip(el); });
    el.addEventListener("pointerleave", hideTip);
    el.addEventListener("focus", function () { showTip(el); });
    el.addEventListener("blur", hideTip);
  });
  window.addEventListener("scroll", hideTip, { passive: true });

  // Regnestykket i lagerskjemaet
  var form = document.getElementById("item-form");
  if (form) {
    var nf = new Intl.NumberFormat("nb-NO", { maximumFractionDigits: 0 });
    var kr = function (n) { return (n < 0 ? "−" : "") + nf.format(Math.abs(n)) + " kr"; };
    var num = function (name) {
      var el = form.elements[name];
      if (!el) return null;
      var text = String(el.value).split(",")[0].replace(/[^\d-]/g, "");
      return text === "" || text === "-" ? null : parseInt(text, 10);
    };
    var out = function (name) { return form.querySelector('[data-out="' + name + '"]'); };
    var update = function () {
      var purchase = num("purchase_price");
      var extras = ["cost_grip", "cost_shipping", "cost_cleaning", "cost_other"]
        .reduce(function (sum, name) { return sum + (num(name) || 0); }, 0);
      var cost = (purchase || 0) + extras;
      var status = form.elements.status.value;
      var sale = num("sale_price");
      var listed = num("listed_price");
      var income = status === "solgt" ? sale : listed;
      out("purchase").textContent = purchase === null ? "–" : kr(purchase);
      out("extras").textContent = kr(extras);
      out("cost").textContent = kr(cost);
      out("income-label").textContent = status === "solgt" ? "Salgspris" : "Utlagt pris";
      out("income").textContent = income === null ? "–" : kr(income);
      var profitEl = out("profit");
      profitEl.className = "";
      if (income === null) {
        profitEl.textContent = "–";
        out("note").textContent = status === "solgt" ? "Fyll inn salgsprisen." : "Fyll inn utlagt pris for å se hva du tjener.";
      } else {
        var profit = income - cost;
        profitEl.textContent = (profit > 0 ? "+" : "") + kr(profit);
        profitEl.className = profit > 0 ? "pos" : profit < 0 ? "neg" : "";
        var pct = cost > 0 ? Math.round(profit / cost * 100) : null;
        out("note").textContent = (status === "solgt" ? "" : "Hvis den selges for utlagt pris. ") +
          (pct === null ? "" : "Det er " + pct + " % av det du har lagt ut.");
      }
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }

  // Oppdater Finn-søk-siden når scraperen er ferdig
  var status = document.querySelector("[data-scraper-status]");
  if (status && window.fetch) {
    var wasRunning = status.getAttribute("data-running") === "1";
    var polls = 0;
    var typing = function () {
      var active = document.activeElement;
      if (active && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return true;
      var url = document.getElementById("url");
      return !!(url && url.value);
    };
    var poll = function () {
      polls += 1;
      fetch("/api/status", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (data) {
        if (data.running !== wasRunning && !typing()) { window.location.reload(); return; }
        if (polls < 90) setTimeout(poll, wasRunning ? 3000 : 6000);
      }).catch(function () {});
    };
    setTimeout(poll, 3000);
  }
})();
