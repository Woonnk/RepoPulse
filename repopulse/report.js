"use strict";
const report = JSON.parse(document.getElementById("report-data").textContent);
const byId = id => document.getElementById(id);
const number = value => value.toLocaleString();
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const locationLink = (path, line) => {
  const node = element(report.source_links[path] ? "a" : "span", path + (line ? ":" + line : ""), "location");
  if (report.source_links[path]) {
    node.href = report.source_links[path];
    node.title = line ? "Open local file; marker is at line " + line : "Open local file";
  }
  return node;
};
byId("project").textContent = report.project;
document.title = report.project + " | RepoPulse";
byId("scope").textContent = report.git_ignore_applied ? "Git inventory with ignore rules applied" : "Filesystem inventory with built-in exclusions";
byId("score").textContent = report.score === null ? "Not scored" : report.score + " / 100";
byId("progress").value = report.score || 0;
byId("progress").hidden = report.score === null;
for (const [label, value] of [["files", report.file_count], ["bytes", report.total_bytes], ["findings", report.findings.length], ["markers", report.marker_count]]) {
  const stat = element("span");
  stat.append(element("strong", number(value)), document.createTextNode(" " + label));
  byId("stats").append(stat);
}
for (const project of report.projects) {
  const node = element("div", undefined, "project");
  node.append(element("strong", project.type), document.createTextNode(" / " + project.directory));
  if (project.frameworks.length) node.append(element("div", project.frameworks.join(", "), "muted"));
  node.append(locationLink(project.path), element("span", "Manifest: " + project.manifest_status, "muted"));
  byId("projects").append(node);
}
for (const [language, count] of Object.entries(report.languages)) byId("languages").append(element("span", language + " " + number(count)));
for (const check of report.checks) byId("basics").append(element("span", (check.enabled ? (check.passed ? "Pass: " : "Missing: ") : "Disabled: ") + check.label, check.enabled ? (check.passed ? "pass" : "miss") : "off"));
const warnings = [...report.warnings, ...(report.comparison ? report.comparison.warnings : [])];
for (const warning of warnings) byId("warnings").append(element("div", warning, "notice"));
byId("footer").textContent = "Content skipped: " + number(report.skipped_content_files) + " files. Marker locations shown: " + number(report.markers.length) + " of " + number(report.marker_count) + ". Source links open local files; line numbers are displayed here. Reports may contain private paths and snippets.";

let view = "findings", page = 0;
const pageSize = 50;
const tabs = ["findings", "files", "markers", "changes"];
const markers = report.markers.map(marker => ({...marker, severity: "info", title: marker.kind, suggestion: marker.text, evidence: null}));
const changes = [];
if (report.comparison) {
  const diff = report.comparison;
  for (const [key, label, severity] of [["new_findings", "New finding", "warning"], ["resolved_findings", "Resolved finding", "info"]]) {
    for (const finding of diff[key]) changes.push({...finding, severity: key === "new_findings" ? finding.severity : severity, title: label + ": " + finding.title});
  }
  for (const [key, label] of [["new_markers", "New marker"], ["resolved_markers", "Resolved marker"]]) {
    for (const marker of diff[key]) changes.push({severity: "info", title: label + ": " + marker.kind + " (" + marker.count + ")", path: marker.path, line: marker.line, suggestion: marker.text || "Snippet omitted by the marker output limit.", evidence: null});
  }
  for (const file of diff.grown_files) changes.push({severity: "info", title: "File grew by " + number(file.delta) + " bytes", path: file.path, suggestion: number(file.before_bytes) + " to " + number(file.after_bytes) + " bytes"});
  for (const path of diff.added_files) changes.push({severity: "info", title: "Added to inventory", path, suggestion: "File is present in this scan."});
  for (const path of diff.removed_files) changes.push({severity: "info", title: "Removed from inventory", path, suggestion: "File was deleted or is no longer in the scan scope."});
  byId("change-summary").textContent = "Score change: " + (diff.score_delta === null ? "not comparable" : (diff.score_delta >= 0 ? "+" : "") + diff.score_delta) + " | Size change: " + (diff.bytes_delta >= 0 ? "+" : "") + number(diff.bytes_delta) + " bytes | Content not compared: " + number(diff.uncompared_content_files.length) + " files";
}
const row = finding => {
  const node = element("article", undefined, "row");
  node.append(element("span", finding.severity, "badge " + finding.severity));
  const body = element("div", undefined, "row-body");
  body.append(element("h3", finding.title));
  if (finding.path) body.append(locationLink(finding.path, finding.line));
  if (finding.evidence) body.append(element("div", finding.evidence, "evidence"));
  body.append(element("p", finding.suggestion, "suggestion"));
  node.append(body);
  return node;
};
function refresh() {
  const query = byId("search").value.toLowerCase();
  const severity = byId("severity").value;
  let values = view === "files" ? [...report.files] : view === "changes" ? changes : view === "markers" ? markers : report.findings;
  values = values.filter(value => [value.path, value.title, value.suggestion, value.evidence].filter(Boolean).join(" ").toLowerCase().includes(query) && (view !== "findings" || severity === "all" || value.severity === severity));
  if (view === "files") values.sort(byId("sort").value === "size" ? (a, b) => b.bytes - a.bytes || a.path.localeCompare(b.path) : (a, b) => a.path.localeCompare(b.path));
  page = Math.min(page, Math.max(0, Math.ceil(values.length / pageSize) - 1));
  const selected = values.slice(page * pageSize, (page + 1) * pageSize);
  const results = byId("results");
  results.replaceChildren();
  byId("severity").disabled = view !== "findings";
  byId("sort-label").hidden = view !== "files";
  byId("change-summary").hidden = view !== "changes" || !report.comparison;
  if (!values.length) results.append(element("div", view === "changes" && !report.comparison ? "No baseline supplied. Scan with --baseline to compare changes." : query || (view === "findings" && severity !== "all") ? "No matching results." : view === "findings" ? "No enabled checks produced findings." : "No items to show.", "empty"));
  else if (view === "files") {
    const wrap = element("div", undefined, "table-wrap");
    const table = element("table");
    const head = element("thead"), headers = element("tr");
    for (const title of ["File", "Bytes", "Content scan"]) {
      const cell = element("th", title); cell.scope = "col"; headers.append(cell);
    }
    head.append(headers); table.append(head);
    const body = element("tbody");
    for (const file of selected) {
      const tr = element("tr"), path = element("td");
      path.append(locationLink(file.path));
      tr.append(path, element("td", number(file.bytes)), element("td", file.content_scanned ? "Scanned" : "Skipped / unread"));
      body.append(tr);
    }
    table.append(body); wrap.append(table); results.append(wrap);
  } else for (const finding of selected) results.append(row(finding));
  byId("result-count").textContent = values.length ? number(page * pageSize + 1) + "-" + number(Math.min((page + 1) * pageSize, values.length)) + " of " + number(values.length) : "0 results";
  byId("previous").disabled = page === 0;
  byId("next").disabled = (page + 1) * pageSize >= values.length;
}
function selectTab(next) {
  view = next; page = 0;
  for (const tab of tabs) {
    byId("tab-" + tab).setAttribute("aria-selected", String(tab === view));
    byId("tab-" + tab).tabIndex = tab === view ? 0 : -1;
  }
  byId("results").setAttribute("aria-labelledby", "tab-" + view);
  refresh();
}
for (const tab of tabs) {
  byId("tab-" + tab).addEventListener("click", () => selectTab(tab));
  byId("tab-" + tab).addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (tabs.indexOf(tab) + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    selectTab(tabs[index]); byId("tab-" + tabs[index]).focus();
  });
}
for (const id of ["search", "severity", "sort"]) byId(id).addEventListener(id === "search" ? "input" : "change", () => {page = 0; refresh();});
byId("previous").addEventListener("click", () => {page--; refresh();});
byId("next").addEventListener("click", () => {page++; refresh();});
refresh();
