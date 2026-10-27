/* AI & Digital Readiness Scorecard — lead magnet
   12 questions x 4 dimensions, 0–3 points each -> 0–100 score.
   Score shown instantly; the personal roadmap is unlocked with an email
   (lead goes to the Google Sheet with all answers, so the follow-up can be specific). */
(function () {
  "use strict";
  var root = document.getElementById("scorecard");
  if (!root) return;
  var dl = function (o) { (window.dataLayer = window.dataLayer || []).push(o); };

  var DIMS = {
    strategy: "Strategy & ownership",
    data: "Data foundation",
    process: "Process automation",
    people: "People & adoption"
  };
  var Q = [
    { d: "strategy", t: "Who owns AI and digital initiatives in your company today?", o: ["Nobody in particular", "IT handles it when there is time", "A manager owns it part-time", "A C-level owner with budget and a roadmap"] },
    { d: "strategy", t: "Is there a written 12-month roadmap for AI / automation tied to business goals?", o: ["No", "Ideas, not written down", "A list of projects without priorities", "Yes — prioritised by impact and reviewed quarterly"] },
    { d: "strategy", t: "How do you decide which processes to automate first?", o: ["We don't, yet", "Whoever shouts loudest", "Gut feeling of management", "Scored by time saved, revenue impact and risk"] },
    { d: "data", t: "How do managers get weekly KPIs (sales, production/delivery, cash)?", o: ["They ask people and wait", "Manual spreadsheets compiled by someone", "Some dashboards, partly manual", "Live dashboards refreshed automatically"] },
    { d: "data", t: "How many 'sources of truth' exist for the same number (e.g. revenue, leads)?", o: ["We don't know", "Several, they often disagree", "Two or three, reconciled manually", "One agreed source per metric"] },
    { d: "data", t: "Can you trace a closed deal back to the marketing channel and campaign that produced it?", o: ["No", "Only for some channels", "Mostly, with manual work", "Yes, automatically, incl. revenue/margin per channel"] },
    { d: "process", t: "How much of your team's week goes to copy-paste, reporting and status-chasing?", o: ["More than 30%", "15–30%", "5–15%", "Under 5%"] },
    { d: "process", t: "Are your CRM / ERP / spreadsheets connected via APIs or automations?", o: ["No, all manual", "A few email or Zapier-style links", "Key systems connected, gaps remain", "Integrated, with monitored data pipelines"] },
    { d: "process", t: "Do you already run any AI agent in production (support, sales research, content, ops)?", o: ["No", "People use ChatGPT/Claude individually", "One pilot running", "Several agents with owners and KPIs"] },
    { d: "people", t: "How do employees feel about AI and automation?", o: ["Afraid or sceptical", "Curious but untrained", "Some champions in teams", "It's part of how we work, with clear rules"] },
    { d: "people", t: "Is there a policy for what data may be used with AI tools?", o: ["No", "Informal 'be careful'", "Draft policy", "Approved policy, tools and access controls"] },
    { d: "people", t: "How fast can you go from an approved idea to a working pilot?", o: ["Months or never", "2–3 months", "4–8 weeks", "Under 4 weeks"] }
  ];

  var answers = new Array(Q.length).fill(null);
  var idx = 0;
  var qWrap = root.querySelector("[data-questions]");
  var bar = root.querySelector(".progress i");
  var counter = root.querySelector("[data-counter]");
  var back = root.querySelector("[data-back]");
  var resultEl = root.querySelector("[data-result]");
  var started = false;

  Q.forEach(function (q, i) {
    var div = document.createElement("div");
    div.className = "q" + (i === 0 ? " active" : "");
    div.innerHTML = '<p class="eyebrow">' + DIMS[q.d] + '</p><h3>' + q.t + '</h3><div class="opts"></div>';
    var opts = div.querySelector(".opts");
    q.o.forEach(function (label, v) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "opt"; b.textContent = label;
      b.addEventListener("click", function () { choose(i, v, b); });
      opts.appendChild(b);
    });
    qWrap.appendChild(div);
  });

  function show(i) {
    var all = qWrap.querySelectorAll(".q");
    all.forEach(function (el, k) { el.classList.toggle("active", k === i); });
    bar.style.width = (i / Q.length * 100) + "%";
    counter.textContent = (i + 1) + " / " + Q.length;
    back.style.visibility = i === 0 ? "hidden" : "visible";
  }
  function choose(i, v, btn) {
    if (!started) { started = true; dl({ event: "scorecard_start" }); }
    answers[i] = v;
    btn.parentNode.querySelectorAll(".opt").forEach(function (o) { o.classList.remove("sel"); });
    btn.classList.add("sel");
    setTimeout(function () {
      if (i < Q.length - 1) { idx = i + 1; show(idx); } else { finish(); }
    }, 220);
  }
  back.addEventListener("click", function () { if (idx > 0) { idx--; show(idx); } });

  function compute() {
    var per = {}, tot = 0;
    Object.keys(DIMS).forEach(function (k) { per[k] = { s: 0, m: 0 }; });
    Q.forEach(function (q, i) { per[q.d].s += answers[i] || 0; per[q.d].m += 3; tot += answers[i] || 0; });
    var pct = {};
    Object.keys(per).forEach(function (k) { pct[k] = Math.round(per[k].s / per[k].m * 100); });
    return { total: Math.round(tot / (Q.length * 3) * 100), dims: pct };
  }
  function level(s) {
    if (s < 30) return ["Starting line", "Big, cheap wins are still on the table. The first 90 days should focus on one owner, one source of truth for core KPIs, and one well-chosen AI pilot."];
    if (s < 55) return ["Experimenting", "You have pieces in place but they don't compound yet. Connecting data and giving AI work a clear owner usually unlocks the next jump."];
    if (s < 80) return ["Scaling", "Solid foundations. The opportunity now is orchestration: agents that work across systems, and a roadmap measured in hours saved and revenue gained."];
    return ["Leading", "You're ahead of most mid-market companies. Focus on governance, AI-native operating model and turning internal capabilities into competitive advantage."];
  }

  function finish() {
    bar.style.width = "100%";
    var r = compute();
    var lv = level(r.total);
    qWrap.style.display = "none";
    root.querySelector(".qnav").style.display = "none";
    resultEl.hidden = false;
    var C = 2 * Math.PI * 64;
    resultEl.querySelector("[data-ring]").innerHTML =
      '<svg viewBox="0 0 150 150" width="150" height="150"><circle cx="75" cy="75" r="64" stroke="rgba(255,255,255,.1)" stroke-width="12" fill="none"/>' +
      '<circle cx="75" cy="75" r="64" stroke="url(#gr)" stroke-width="12" fill="none" stroke-linecap="round" stroke-dasharray="' + C + '" stroke-dashoffset="' + (C * (1 - r.total / 100)) + '"/>' +
      '<defs><linearGradient id="gr" x1="0" x2="1"><stop offset="0" stop-color="#2dd4bf"/><stop offset="1" stop-color="#7c83ff"/></linearGradient></defs></svg><b>' + r.total + '</b>';
    resultEl.querySelector("[data-level]").textContent = lv[0];
    resultEl.querySelector("[data-level-text]").textContent = lv[1];
    var dims = resultEl.querySelector("[data-dims]");
    dims.innerHTML = Object.keys(DIMS).map(function (k) {
      return '<div class="dim"><span>' + DIMS[k] + '</span><div class="bar"><i style="width:' + r.dims[k] + '%"></i></div><b>' + r.dims[k] + '</b></div>';
    }).join("");
    var form = resultEl.querySelector("form");
    form.querySelector("[name=score_total]").value = r.total;
    form.querySelector("[name=score_dims]").value = JSON.stringify(r.dims);
    form.querySelector("[name=answers]").value = JSON.stringify(Q.map(function (q, i) { return { q: q.t, a: q.o[answers[i]] }; }));
    dl({ event: "scorecard_complete", score: r.total, score_level: lv[0] });
  }
  show(0);
})();
