const $ = (id) => document.getElementById(id);
const files = { report: null, model: null };
let excel = null;

function pick(key, file) {
  if (!file) return;
  files[key] = file;
  const zone = $(key === "report" ? "dropReport" : "dropModel");
  $(key === "report" ? "nameReport" : "nameModel").textContent = file.name;
  zone.classList.add("filled");
  $("go").disabled = !(files.report && files.model);
  $("error").hidden = true;
}

for (const [key, zoneId] of [["report", "dropReport"], ["model", "dropModel"]]) {
  const zone = $(zoneId), input = $(key);
  input.addEventListener("change", () => pick(key, input.files[0]));
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("over");
  });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove("over");
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("over");
    if (event.dataTransfer.files[0]) pick(key, event.dataTransfer.files[0]);
  });
}

function tagClass(status) {
  if (status === "OK" || status === "Report-level measure" || status === "Compatible") return "ok";
  if (status === "OK (case differs)") return "warn";
  if (/^Missing|mismatch|Moved|Will break|Not compatible/.test(status)) return "bad";
  return "warn";
}

function fill(tableId, rows, columns, emptyText) {
  const table = $(tableId);
  table.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.className = "empty";
    cell.colSpan = columns.length;
    cell.textContent = emptyText;
    row.append(cell);
    table.append(row);
    return;
  }

  const head = document.createElement("tr");
  columns.forEach(([label]) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  });
  table.append(head);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach(([, key, isTag]) => {
      const cell = document.createElement("td");
      const value = row[key] ?? "";
      if (isTag && value) {
        const badge = document.createElement("span");
        badge.className = `tag ${tagClass(value)}`;
        badge.textContent = value;
        cell.append(badge);
      } else {
        cell.textContent = value;
      }
      tr.append(cell);
    });
    table.append(tr);
  });
}

function showError(message) {
  const error = $("error");
  error.textContent = message;
  error.hidden = !message;
}

async function checkServer() {
  const status = $("serverStatus");
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("Health check failed");
    status.classList.add("is-online");
    status.classList.remove("is-offline");
    $("serverStatusText").textContent = "Local checker ready";
  } catch {
    status.classList.add("is-offline");
    status.classList.remove("is-online");
    $("serverStatusText").textContent = "Local checker unavailable";
  }
}

function setActiveTab(tab) {
  document.querySelectorAll(".result-tab").forEach((button) => {
    const active = button === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    $(button.getAttribute("aria-controls")).hidden = !active;
  });
}

document.querySelectorAll(".result-tab").forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => setActiveTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(index + direction + tabs.length) % tabs.length];
    next.focus();
    setActiveTab(next);
  });
});

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  $("result").hidden = true;
  const button = $("go");
  button.disabled = true;
  button.classList.add("loading");
  button.setAttribute("aria-busy", "true");
  button.querySelector("span:first-child").textContent = "Comparing your files…";
  const body = new FormData();
  body.append("report", files.report);
  body.append("model", files.model);

  try {
    const response = await fetch("/api/check", { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "The comparison failed.");
    render(data);
  } catch (error) {
    showError(error instanceof TypeError
      ? "Could not reach the local checker. Make sure the Python server is running, then try again."
      : error.message);
  } finally {
    button.classList.remove("loading");
    button.removeAttribute("aria-busy");
    button.querySelector("span:first-child").textContent = "Check compatibility";
    button.disabled = !(files.report && files.model);
  }
});

function render(data) {
  excel = data;
  const verdictClass = tagClass(data.verdict);
  const explanations = {
    "Not compatible": `${data.summary["Breaking problems"]} field(s) are missing or different in the target model.`,
    "Compatible with warnings": "Nothing is missing, but a few items need a manual look.",
    "Compatible": "Every field the report uses exists in the target model."
  };
  $("verdict").className = `verdict ${verdictClass}`;
  $("verdict").replaceChildren(document.createTextNode(data.verdict));
  const explanation = document.createElement("small");
  explanation.textContent = explanations[data.verdict] || "";
  $("verdict").append(explanation);

  $("stats").replaceChildren();
  Object.entries(data.summary).forEach(([label, value]) => {
    const box = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    box.append(term, detail);
    $("stats").append(box);
  });

  $("meta").textContent = `${data.meta["Report file"]} · ${data.meta["Target model file"]} · ${data.meta["Target model tables"]} model tables`;
  $("problemCount").textContent = data.problems.length;
  $("visualCount").textContent = data.visuals.length;
  $("warningCount").textContent = data.warnings.length;
  fill("problems", data.problems, [["Table", "Table"], ["Field", "Field"], ["Kind", "Kind"], ["Status", "Status", true], ["Detail", "Note"], ["Visuals", "Used in visuals"]], "No breaking problems found.");
  fill("visuals", data.visuals, [["Page", "Page"], ["Visual", "Visual"], ["Type", "Visual type"], ["Result", "Result", true], ["Problem fields", "Problem fields"], ["Relationship note", "Relationship note"]], "No visuals found.");
  fill("warnings", data.warnings, [["Table", "Table"], ["Field", "Field"], ["Status", "Status", true], ["Detail", "Note"]], "No warnings.");
  setActiveTab(document.querySelector(".result-tab"));
  $("result").hidden = false;
  $("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("download").addEventListener("click", () => {
  if (!excel) return;
  const bytes = Uint8Array.from(atob(excel.excel_base64), (char) => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: excel.filename });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});

checkServer();
