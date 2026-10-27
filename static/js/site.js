/* CRO Accelerate — site behaviour
   - nav toggle, reveal-on-scroll, glass pointer highlight
   - Consent Mode v2 banner (EU-friendly)
   - attribution capture (UTM / gclid / li_fat_id / referrer / landing page)
   - lead forms -> Google Apps Script -> Google Sheet
   - dataLayer events for GTM: cta_click, generate_lead, calendly_*
*/
(function () {
  "use strict";
  var CFG = window.SITE_CFG || {};
  window.dataLayer = window.dataLayer || [];
  function dl(o) { window.dataLayer.push(o); }
  document.documentElement.classList.remove("no-js");

  /* ---------- Nav ---------- */
  var nav = document.querySelector(".nav");
  var toggle = document.querySelector(".nav-toggle");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ---------- Reveal ---------- */
  var els = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { io.observe(el); });
  } else { els.forEach(function (el) { el.classList.add("in"); }); }

  /* ---------- Glass specular highlight follows pointer ---------- */
  if (window.matchMedia("(hover:hover)").matches) {
    document.addEventListener("pointermove", function (ev) {
      var g = ev.target.closest && ev.target.closest(".glass");
      if (!g) return;
      var r = g.getBoundingClientRect();
      g.style.setProperty("--mx", ((ev.clientX - r.left) / r.width * 100) + "%");
      g.style.setProperty("--my", ((ev.clientY - r.top) / r.height * 100) + "%");
    }, { passive: true });
  }

  /* ---------- Sticky mobile CTA ---------- */
  var sticky = document.querySelector(".sticky-cta");
  if (sticky && !document.querySelector("form[data-lead-form]")) {
    window.addEventListener("scroll", function () {
      sticky.classList.toggle("show", window.scrollY > 700);
    }, { passive: true });
  }

  /* ---------- Consent Mode v2 ---------- */
  var CONSENT_KEY = "cra_consent_v1";
  function readConsent() { try { return localStorage.getItem(CONSENT_KEY); } catch (e) { return null; } }
  function saveConsent(v) { try { localStorage.setItem(CONSENT_KEY, v); } catch (e) {} }
  function applyConsent(v) {
    var granted = v === "all" ? "granted" : "denied";
    if (typeof window.gtag === "function") {
      window.gtag("consent", "update", {
        ad_storage: granted, ad_user_data: granted, ad_personalization: granted,
        analytics_storage: (v === "all" || v === "analytics") ? "granted" : "denied"
      });
    }
    dl({ event: "consent_update", consent_choice: v });
  }
  var banner = document.querySelector(".cookie");
  var stored = readConsent();
  if (stored) { applyConsent(stored); }
  else if (banner) { banner.classList.add("show"); }
  document.querySelectorAll("[data-consent]").forEach(function (b) {
    b.addEventListener("click", function () {
      var v = b.getAttribute("data-consent");
      saveConsent(v); applyConsent(v);
      if (banner) banner.classList.remove("show");
    });
  });
  document.querySelectorAll("[data-open-consent]").forEach(function (a) {
    a.addEventListener("click", function (e) { e.preventDefault(); if (banner) banner.classList.add("show"); });
  });

  /* ---------- Attribution capture (first touch + last touch) ---------- */
  var ATTR_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "gbraid", "wbraid", "li_fat_id", "fbclid", "msclkid"];
  function getAttr() {
    var params = new URLSearchParams(location.search);
    var last = {};
    ATTR_KEYS.forEach(function (k) { if (params.get(k)) last[k] = params.get(k).slice(0, 200); });
    var first = null;
    try { first = JSON.parse(localStorage.getItem("cra_first_touch") || "null"); } catch (e) {}
    if (!first) {
      first = Object.assign({}, last, {
        landing_page: location.pathname,
        referrer: document.referrer ? document.referrer.slice(0, 300) : "(direct)",
        ts: new Date().toISOString()
      });
      try { localStorage.setItem("cra_first_touch", JSON.stringify(first)); } catch (e) {}
    }
    if (Object.keys(last).length) { try { sessionStorage.setItem("cra_last_touch", JSON.stringify(last)); } catch (e) {} }
    var lastStored = {};
    try { lastStored = JSON.parse(sessionStorage.getItem("cra_last_touch") || "{}"); } catch (e) {}
    return { first: first, last: lastStored };
  }
  var ATTR = getAttr();
  window.CRA_ATTR = ATTR;

  /* ---------- CTA click tracking ---------- */
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a, button");
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (a.hasAttribute("data-cta")) {
      dl({ event: "cta_click", cta_id: a.getAttribute("data-cta"), cta_text: (a.textContent || "").trim().slice(0, 80), cta_url: href });
    }
    if (href.indexOf("calendly.com") > -1) {
      dl({ event: "calendly_open", cta_id: a.getAttribute("data-cta") || "calendly_link" });
      var url = new URL(href, location.href);
      ["utm_source", "utm_medium", "utm_campaign"].forEach(function (k) {
        var v = (ATTR.last && ATTR.last[k]) || (ATTR.first && ATTR.first[k]);
        if (v && !url.searchParams.get(k)) url.searchParams.set(k, v);
      });
      a.setAttribute("href", url.toString());
    }
    if (href.indexOf("mailto:") === 0) dl({ event: "email_click" });
    if (href.indexOf("linkedin.com") > -1) dl({ event: "linkedin_click" });
  });

  /* ---------- Calendly embed events (booking = primary conversion) ---------- */
  window.addEventListener("message", function (e) {
    if (!e.data || typeof e.data.event !== "string" || e.data.event.indexOf("calendly.") !== 0) return;
    var map = { "calendly.date_and_time_selected": "calendly_time_selected", "calendly.event_scheduled": "calendly_booking" };
    if (map[e.data.event]) {
      dl({ event: map[e.data.event], lead_type: "call_booked" });
      if (e.data.event === "calendly.event_scheduled") {
        sendLead({ form_name: "calendly", lead_type: "call_booked", message: "Booked via Calendly embed" });
      }
    }
  });

  /* ---------- Lead submission ---------- */
  function sendLead(payload) {
    if (!CFG.leadEndpoint) return Promise.reject(new Error("no endpoint"));
    var body = Object.assign({
      page: location.pathname,
      page_title: document.title,
      submitted_at: new Date().toISOString(),
      tz: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
      lang: navigator.language || "",
      first_touch: JSON.stringify(ATTR.first || {}),
      last_touch: JSON.stringify(ATTR.last || {})
    }, payload);
    // text/plain avoids a CORS preflight against Apps Script
    return fetch(CFG.leadEndpoint, { method: "POST", mode: "no-cors", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(body) });
  }
  window.CRA_sendLead = sendLead;

  var started = Date.now();
  document.querySelectorAll("form[data-lead-form]").forEach(function (form) {
    var msg = form.querySelector(".form-msg");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (form.querySelector(".hp input") && form.querySelector(".hp input").value) return; // honeypot
      if (Date.now() - started < 3000) return; // too fast = bot
      if (!form.checkValidity()) { form.reportValidity(); return; }
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = String(v).slice(0, 4000); });
      data.form_name = form.getAttribute("data-lead-form");
      data.lead_type = data.lead_type || form.getAttribute("data-lead-type") || "contact";
      var btn = form.querySelector("button[type=submit]");
      if (btn) { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = "Sending…"; }
      sendLead(data).then(function () {
        dl({ event: "generate_lead", form_name: data.form_name, lead_type: data.lead_type, company_size: data.company_size || "", interest: data.interest || "" });
        if (form.hasAttribute("data-redirect")) { location.href = form.getAttribute("data-redirect"); return; }
        if (msg) { msg.className = "form-msg ok"; msg.textContent = "Thank you — we'll reply within one business day."; }
        form.reset();
      }).catch(function () {
        if (msg) { msg.className = "form-msg err"; msg.innerHTML = "Something went wrong. Please email <a href=\"mailto:" + (CFG.email || "") + "\">" + (CFG.email || "me") + "</a>."; }
      }).finally(function () {
        if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label; }
      });
    });
  });

  /* ---------- Scroll depth (lightweight, for content scoring) ---------- */
  var marks = [50, 90], fired = {};
  window.addEventListener("scroll", function () {
    var h = document.documentElement;
    var pct = (h.scrollTop + window.innerHeight) / h.scrollHeight * 100;
    marks.forEach(function (m) {
      if (pct >= m && !fired[m]) { fired[m] = 1; dl({ event: "scroll_depth", percent: m, page_type: document.body.dataset.pageType || "" }); }
    });
  }, { passive: true });
})();
