// Small helpers shared across the explorer. No dependencies.

export function parseCSV(text) {
  const rows = [];
  let row = [], cell = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') inQ = false;
      else cell += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else cell += c;
  }
  row.push(cell);
  if (row.length > 1 || row[0] !== "") rows.push(row);
  return rows;
}

export const pct = (x) => `${Math.round((x ?? 0) * 100)}%`;

export const stable = (v) =>
  JSON.stringify(v, v && typeof v === "object" && !Array.isArray(v)
    ? Object.keys(v).sort() : undefined);

export const sourceOf = (recordId) => recordId.split("#")[0];

export function clusterSourceIds(cand) {
  return [...new Set(cand.cluster.record_ids.map(sourceOf))];
}

/** Atoms behind a selection {key, el} against a candidate's debug map. */
export function atomsFor(cand, sel) {
  const entry = cand.debug[sel.key];
  if (!entry) return [];
  if (entry.kind === "set") {
    if (sel.el != null) return entry.elements[sel.el]?.atoms ?? [];
    return entry.elements.flatMap((e) => e.atoms);
  }
  return entry.atoms ?? [];
}

/** Why is this field empty? Pull matching run-report entries. */
export function emptyReasons(bundle, cand, fieldPrefix) {
  const srcs = new Set(clusterSourceIds(cand));
  return (bundle.unparseable ?? []).filter(
    (u) =>
      u.field.startsWith(fieldPrefix) &&
      (srcs.has(u.source_id) || u.candidate_id === cand.candidate_id)
  );
}

export const SOURCE_ICONS = {
  recruiter_csv: "▤", ats_json: "{}", notes_txt: "✎", resume: "📄",
  github_json: "⌥", linkedin_json: "in", derived: "ƒ",
};

/** Download an object as JSON, mirroring report.write_json's conventions
 *  (sorted keys, indent 2, trailing newline) so a UI download diffs cleanly
 *  against CLI output. */
export function downloadJson(obj, filename) {
  const text = JSON.stringify(sortKeysDeep(obj), null, 2) + "\n";
  const url = URL.createObjectURL(
    new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function sortKeysDeep(v) {
  if (Array.isArray(v)) return v.map(sortKeysDeep);
  if (v && typeof v === "object") {
    const out = {};
    for (const k of Object.keys(v).sort()) out[k] = sortKeysDeep(v[k]);
    return out;
  }
  return v;
}

/** Rebuild the CLI's run_report.json from a UI bundle by stripping the
 *  bundle-only additions: run.profiles and each source's inlined content. */
export function runReportOf(bundle) {
  const { profiles: _count, ...run } = bundle.run;
  return {
    run,
    sources: bundle.sources.map(({ content: _c, ...s }) => s),
    unrecognized_files: bundle.unrecognized_files,
    merges: bundle.merges,
    validation: bundle.validation,
    unparseable: bundle.unparseable,
  };
}

/** Button semantics for clickable non-button elements (a11y + keyboard). */
export function pressable(onActivate) {
  return {
    role: "button",
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate(e);
      }
    },
  };
}

export function refusalsTouching(bundle, cand) {
  const ids = new Set(cand.cluster.record_ids);
  return (bundle.merges?.refusals ?? []).filter((r) =>
    r.records.some((rid) => ids.has(rid))
  );
}
