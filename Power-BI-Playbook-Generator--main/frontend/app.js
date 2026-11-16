(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const views = ["upload", "progress", "issues", "playbook"];
  const state = { file: null, steps: [], jobId: null, pollTimer: null, observer: null };

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  function show(name) {
    views.forEach((v) => ($("#view-" + v).hidden = v !== name));
    window.scrollTo({ top: 0 });
  }

  // ---------------------------------------------------------------- setup
  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => {
      state.steps = cfg.steps;
      const note = $("#model-note");
      note.textContent = cfg.demo_mode ? "Demo mode is on: a sample playbook is shown instead of calling the AI." : `AI model: ${cfg.model}`;
      note.hidden = false;
    })
    .catch(() => {
      state.steps = [{ key: "validate", label: "Reading the BRD" },
                     { key: "data_foundation", label: "Designing sources, tables and relationships" },
                     { key: "measures_pages", label: "Writing KPI DAX and report pages" },
                     { key: "access_delivery", label: "Planning security, refresh, deployment and delivery" },
                     { key: "pdf", label: "Building the PDF" }];
    });

  // ---------------------------------------------------------------- upload
  const dz = $("#dropzone");
  const input = $("#file-input");

  function setFile(f) {
    $("#upload-error").hidden = true;
    const okTypes = [".xlsx", ".xlsm", ".docx", ".pdf", ".csv", ".txt", ".md"];
    if (f && !okTypes.some((t) => f.name.toLowerCase().endsWith(t))) {
      showUploadError("Please choose an Excel, Word, PDF, CSV or text file.");
      f = null;
    }
    state.file = f || null;
    $("#file-chip").hidden = !state.file;
    dz.hidden = !!state.file;
    $("#file-name").textContent = state.file ? state.file.name : "";
    $("#btn-generate").disabled = !state.file;
  }
  function showUploadError(msg) {
    const el = $("#upload-error");
    el.textContent = msg;
    el.hidden = false;
  }

  input.addEventListener("change", () => setFile(input.files[0]));
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  $("#file-clear").addEventListener("click", (e) => { e.preventDefault(); input.value = ""; setFile(null); });

  $("#btn-generate").addEventListener("click", async () => {
    if (!state.file) return;
    const btn = $("#btn-generate");
    btn.disabled = true;
    btn.textContent = "Reading BRD…";
    const fd = new FormData();
    fd.append("brd", state.file);
    try {
      const res = await fetch("/api/generate", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Something went wrong.");
      state.jobId = data.job_id;
      startProgress();
    } catch (err) {
      showUploadError(err.message || "Could not reach the server. Is it still running?");
    } finally {
      btn.disabled = !state.file;
      btn.textContent = "Generate playbook";
    }
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-action]");
    if (!a) return;
    if (a.dataset.action === "restart") restart();
    if (a.dataset.action === "retry") $("#btn-generate").click();
    if (a.dataset.action === "download") window.location.href = `/api/jobs/${state.jobId}/pdf`;
  });

  function restart() {
    clearInterval(state.pollTimer);
    input.value = "";
    setFile(null);
    show("upload");
  }

  // ---------------------------------------------------------------- errors
  function showError(msg) {
    $("#issues-sub").textContent = msg;
    show("issues");
  }

  // ---------------------------------------------------------------- progress
  function renderSteps(current) {
    const keys = state.steps.map((s) => s.key);
    const idx = current === "done" ? keys.length : Math.max(keys.indexOf(current), 1);
    $("#step-list").innerHTML = state.steps.map((s, i) =>
      `<li class="${i < idx ? "done" : i === idx ? "active" : ""}"><span class="step-dot"></span>${esc(s.label)}</li>`).join("");
  }

  function startProgress() {
    $("#progress-file").textContent = state.file ? state.file.name : "";
    renderSteps("data_foundation");
    $("#progress-detail").hidden = true;
    $("#progress-elapsed").textContent = "";
    show("progress");
    clearInterval(state.pollTimer);
    state.pollTimer = setInterval(poll, 1500);
  }

  async function poll() {
    try {
      const res = await fetch(`/api/jobs/${state.jobId}`);
      const job = await res.json();
      if (!res.ok) throw new Error(job.error);
      renderSteps(job.step);
      const det = $("#progress-detail");
      det.textContent = job.detail || "";
      det.hidden = !job.detail;
      if (job.started) {
        const s = Math.max(0, Math.round(Date.now() / 1000 - job.started));
        $("#progress-elapsed").textContent = `Elapsed: ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
      }
      if (job.status === "done") {
        clearInterval(state.pollTimer);
        renderPlaybook(job.playbook);
      } else if (job.status === "error") {
        clearInterval(state.pollTimer);
        showError(job.error);
      }
    } catch (err) {
      clearInterval(state.pollTimer);
      showError(err.message || "Lost contact with the server.");
    }
  }

  // ---------------------------------------------------------------- playbook rendering
  const table = (headers, rows) =>
    `<div class="table-wrap"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  const kv = (rows) =>
    `<div class="table-wrap"><table class="kv"><tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div>`;
  const list = (items) => (items && items.length ? `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "");
  const note = (paras) => (paras && paras.filter(Boolean).length
    ? `<div class="note"><b>Note</b>${paras.filter(Boolean).map((p) => `<p>${esc(p)}</p>`).join("")}</div>` : "");
  const code = (t) => (t ? `<pre class="code">${esc(t)}</pre>` : "");

  // Same auto-layout as the PDF wireframe (backend/pdf_builder.py: wireframe_blocks)
  function wireframeBlocks(page) {
    const blocks = [[0, 0, 1, 0.12, page.name, "title"]];
    const slicers = String(page.slicers || "").split(",").map((s) => s.trim()).filter((s) => s && s.toLowerCase() !== "none").slice(0, 4);
    const visuals = page.visuals || [];
    const cards = visuals.filter((v) => (v.type || "").toLowerCase().includes("card")).slice(0, 5);
    const others = visuals.filter((v) => !cards.includes(v)).slice(0, 6);
    let y = 0.12;
    if (slicers.length) {
      const w = 1 / slicers.length;
      slicers.forEach((s, i) => blocks.push([i * w, y, w, 0.11, "Slicer: " + s.split("(")[0].trim(), "slicer"]));
      y += 0.11;
    }
    if (cards.length) {
      const w = 1 / cards.length;
      cards.forEach((c, i) => blocks.push([i * w, y, w, 0.17, c.visual, "card"]));
      y += 0.17;
    }
    if (others.length) {
      const cols = others.length === 1 ? 1 : 2;
      const rows = Math.ceil(others.length / cols);
      const rh = (1 - y) / rows;
      others.forEach((v, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        const full = cols === 1 || (i === others.length - 1 && others.length % 2 === 1);
        blocks.push([full ? 0 : c / cols, y + r * rh, full ? 1 : 1 / cols, rh, `${v.visual}\n(${v.type})`, "visual"]);
      });
    }
    return blocks;
  }
  const wireframe = (page) =>
    `<div class="wireframe">${wireframeBlocks(page).map(([x, y, w, h, label, kind]) =>
      `<div class="wf ${kind}" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%"><div>${esc(label)}</div></div>`).join("")}</div>`;

  function buildSections(pb) {
    const dc = pb.doc_control, es = pb.executive_summary, g = es.at_a_glance;
    const S = [];
    const add = (part, id, title, body, subs = []) => S.push({ part, id, title, body, subs });

    add("Part A · Overview", "document-control", "1. Document Control", kv([
      ["Client", dc.client], ["Project", dc.project], ["Business Domain", dc.domain],
      ["Business Owner", dc.business_owner], ["Generated On", dc.generated_on], ["Prepared By", dc.prepared_by]]));

    add("Part A · Overview", "executive-summary", "2. Executive Summary",
      `<h4>Objective</h4><p>${esc(es.objective)}</p><h4>Scope</h4><p>${esc(es.scope)}</p>
       <h3 id="es-glance">At a glance</h3>
       <div class="glance">${[[g.source_systems, "Source systems"], [g.tables, "Tables"], [g.columns, "Columns"], [g.kpis, "KPIs"], [g.report_pages, "Report pages"]]
         .map(([n, l]) => `<div><b>${esc(n)}</b><span>${esc(l)}</span></div>`).join("")}</div>
       <h3 id="es-decisions">Key design decisions</h3>${list(es.key_decisions)}`,
      [["es-glance", "At a glance"], ["es-decisions", "Key design decisions"]]);

    const ss = pb.source_systems;
    add("Part B · Data Foundation", "source-systems", "3. Source System Inventory",
      `<p>Each source system from the BRD, with the recommended connection approach.</p>` +
      table(["Source", "Type", "Owner", "History", "Refresh", "Connector", "Gateway"],
        ss.items.map((i) => [i.source, i.type, i.owner, i.history, i.refresh, i.connector, i.gateway])) + note(ss.notes));

    const t = pb.tables;
    add("Part B · Data Foundation", "tables", "4. Table & Column Catalogue",
      `<h3 id="tables-tables">Tables</h3>` +
      table(["Table (source name)", "Model name", "Role", "Rows", "Power Query transformations"],
        t.items.map((i) => [i.source_table, i.model_name, i.role, i.rows, i.transformations])) +
      `<h3 id="tables-columns">Columns</h3>` +
      table(["Model table", "Column", "Power BI type", "Key", "Notes"], t.columns.map((c) => [c.model_table, c.column, c.pbi_type, c.key, c.notes])),
      [["tables-tables", "Tables"], ["tables-columns", "Columns"]]);

    const dm = pb.data_model;
    add("Part B · Data Foundation", "data-model", "5. Data Model Design",
      `<h3 id="dm-rel">Relationships</h3>` +
      table(["From (many)", "To (one)", "Cardinality", "Cross-filter", "Basis"],
        dm.relationships.map((r) => [r.from, r.to, r.cardinality, r.cross_filter, r.basis])) + note(dm.notes));

    const k = pb.kpis;
    add("Part C · Measures & Report Design", "kpis", "6. KPI & DAX Catalogue",
      `<p>${esc(k.intro)}</p>` +
      (k.base_measures ? `<h3 id="kpi-base">Base measures</h3>${code(k.base_measures)}` : "") +
      k.items.map((i) => `<div class="kpi" id="kpi-${slug(i.name)}">
        <div class="kpi-head"><h3>${esc(i.name)}</h3><span class="badge">Priority: ${esc(i.priority)}</span></div>
        <div class="kpi-body"><dl><dt>Business definition</dt><dd>${esc(i.definition)}</dd><dt>Uses</dt><dd>${esc(i.uses)}</dd></dl>${code(i.dax)}</div>
      </div>`).join(""),
      [...(k.base_measures ? [["kpi-base", "Base measures"]] : []), ...k.items.map((i) => ["kpi-" + slug(i.name), i.name])]);

    const rp = pb.report_pages;
    add("Part C · Measures & Report Design", "report-pages", "7. Report Page Design",
      `<p>${esc(rp.intro)}</p>` +
      rp.pages.map((p) => `<div class="page-block"><h3 id="page-${slug(p.name)}">${esc(p.name)}</h3>` +
        kv([["Purpose", p.purpose], ["Priority", p.priority], ["For personas", p.personas], ["KPIs shown", p.kpis_shown],
            ["Slicers", p.slicers], ["Page filters", p.page_filters], ["Drill-down / drill-through", p.drill], ["Interactions", p.interactions]]) +
        `<h4>Visuals</h4>` + table(["#", "Visual", "Type", "Fields"], p.visuals.map((v, n) => [n + 1, v.visual, v.type, v.fields])) +
        `<h4>Layout wireframe</h4>${wireframe(p)}</div>`).join(""),
      rp.pages.map((p) => ["page-" + slug(p.name), p.name]));

    const a = pb.audience;
    add("Part C · Measures & Report Design", "audience", "8. Audience & Access",
      `<p>${esc(a.source_note)}</p>` +
      (a.personas.length ? table(["Persona", "Users", "Key decisions", "Data access", "Primary pages", "Device"],
        a.personas.map((p) => [p.persona, p.users, p.key_decisions, p.data_access, p.primary_pages, p.device])) : "") +
      (a.recommendations.length ? `<h3 id="aud-rec">Recommendations</h3>${list(a.recommendations)}` : ""),
      a.recommendations.length ? [["aud-rec", "Recommendations"]] : []);

    const sec = pb.security, secSubs = [];
    let secBody = `<p>${esc(sec.source_note)}</p>`;
    if (sec.security_table_description || sec.security_table_columns.length) {
      secSubs.push(["sec-table", "Security table"]);
      secBody += `<h3 id="sec-table">Security table</h3>` + (sec.security_table_description ? `<p>${esc(sec.security_table_description)}</p>` : "") +
        (sec.security_table_columns.length ? table(["Column", "Example", "Notes"], sec.security_table_columns.map((c) => [c.column, c.example, c.notes])) : "");
    }
    if (sec.roles.length) {
      secSubs.push(["sec-roles", "Roles"]);
      secBody += `<h3 id="sec-roles">Roles</h3>` + table(["Role", "Members", "Filter table", "BRD requirement"], sec.roles.map((r) => [r.role, r.members, r.filter_table, r.requirement])) +
        (sec.rls_dax ? `<h4>Role filter expressions</h4>${code(sec.rls_dax)}` : "");
    }
    if (sec.recommendations.length) {
      secSubs.push(["sec-rec", "Additional recommendations"]);
      secBody += `<h3 id="sec-rec">Additional recommendations</h3>${list(sec.recommendations)}`;
    }
    add("Part C · Measures & Report Design", "security", "9. Security & RLS", secBody, secSubs);

    const rf = pb.refresh, rfSubs = [["rf-schedule", "Refresh schedule"]];
    let rfBody = `<h3 id="rf-schedule">Refresh schedule</h3>` + table(["Source", "Required", "Schedule", "Method"], rf.schedule.map((r) => [r.source, r.required, r.schedule, r.method]));
    if (rf.incremental.length) {
      rfSubs.push(["rf-incr", rf.incremental_title || "Incremental refresh"]);
      rfBody += `<h3 id="rf-incr">${esc(rf.incremental_title || "Incremental refresh")}</h3>` + kv(rf.incremental.map((i) => [i.label, i.value]));
    }
    if (rf.practices.length) {
      rfSubs.push(["rf-perf", "Performance practices"]);
      rfBody += `<h3 id="rf-perf">Performance practices</h3>${list(rf.practices)}`;
    }
    add("Part D · Build, Deploy & Deliver", "refresh", "10. Refresh & Performance", rfBody, rfSubs);

    const dp = pb.deployment;
    add("Part D · Build, Deploy & Deliver", "deployment", "11. Deployment & Governance",
      `<h3 id="dep-ws">Workspaces &amp; pipeline</h3>` +
      table(["Stage", "Workspace", "Purpose", "Who has access"], dp.workspaces.map((w) => [w.stage, w.workspace, w.purpose, w.access])) +
      `<p style="margin-top:12px">${esc(dp.pipeline)}</p><h3 id="dep-gov">Governance</h3>${list(dp.governance)}`,
      [["dep-ws", "Workspaces & pipeline"], ["dep-gov", "Governance"]]);

    const dl = pb.delivery;
    add("Part D · Build, Deploy & Deliver", "delivery", "12. Delivery Plan",
      `<p>${esc(dl.intro)}</p>` +
      table(["Sprint", "Goal", "Scope", "Exit criteria"], dl.sprints.map((s) => [s.sprint, s.goal, s.scope, s.exit_criteria])) +
      (dl.dependencies.length ? `<h3 id="del-dep">Dependencies</h3>${list(dl.dependencies)}` : ""),
      dl.dependencies.length ? [["del-dep", "Dependencies"]] : []);
    return S;
  }

  function renderPlaybook(pb) {
    const dc = pb.doc_control;
    const sections = buildSections(pb);

    $("#playbook").innerHTML =
      `<section class="card pb-cover" id="top">
        <div>
          <div class="eyebrow">Playbook ready</div>
          <h1>Power BI Playbook</h1>
          <div class="project">${esc(dc.project)}</div>
          <div class="client">${esc(dc.client)}</div>
        </div>
        <div class="pb-actions">
          <button class="btn btn-primary" data-action="download">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M4 19h16"/></svg>
            Download PDF
          </button>
          <button class="btn btn-secondary" data-action="restart">New playbook</button>
        </div>
      </section>` +
      sections.map((s) => `<section class="card pb-section" id="${s.id}">
        <div class="pb-part">${esc(s.part)}</div><h2>${esc(s.title)}</h2>${s.body}</section>`).join("");

    let lastPart = null;
    $("#toc").innerHTML = sections.map((s) => {
      const part = s.part !== lastPart ? `<div class="toc-part">${esc(s.part.split("·")[1] || s.part)}</div>` : "";
      lastPart = s.part;
      return part + `<a class="toc-link" href="#${s.id}" data-sec="${s.id}">${esc(s.title)}</a>` +
        s.subs.map(([id, label]) => `<a class="toc-sub" href="#${id}" data-sub="${id}" data-parent="${s.id}">${esc(label)}</a>`).join("");
    }).join("");

    show("playbook");
    setupScrollSpy(sections);
  }

  function setupScrollSpy(sections) {
    if (state.observer) state.observer.disconnect();
    const links = document.querySelectorAll(".toc-link, .toc-sub");
    const targets = [];
    sections.forEach((s) => {
      targets.push({ el: document.getElementById(s.id), sec: s.id, sub: null });
      s.subs.forEach(([id]) => targets.push({ el: document.getElementById(id), sec: s.id, sub: id }));
    });

    const update = () => {
      const offset = 120;
      let current = targets[0];
      for (const t of targets) {
        if (t.el && t.el.getBoundingClientRect().top - offset <= 0) current = t;
      }
      if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) current = targets[targets.length - 1];
      links.forEach((l) => {
        const on = l.dataset.sec ? l.dataset.sec === current.sec : l.dataset.sub === current.sub;
        l.classList.toggle("active", on);
      });
      const active = document.querySelector(".toc-link.active");
      const box = document.querySelector(".sidebar-inner");
      if (active && box && box.scrollHeight > box.clientHeight) {
        const r = active.getBoundingClientRect(), b = box.getBoundingClientRect();
        if (r.top < b.top || r.bottom > b.bottom) active.scrollIntoView({ block: "nearest" });
      }
    };
    let ticking = false;
    window.onscroll = () => {
      if (!ticking) { requestAnimationFrame(() => { update(); ticking = false; }); ticking = true; }
    };
    update();
  }
})();
