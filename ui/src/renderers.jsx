import React, { useEffect, useMemo, useRef } from "react";
import { parseCSV } from "./lib.js";

function useScrollToHit(dep) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [dep]);
  return ref;
}

/** Free text with character-span highlights (notes, extracted resume text). */
export function TextPane({ text, spans }) {
  const key = JSON.stringify(spans);
  const firstRef = useScrollToHit(key);
  const sorted = [...spans].sort((a, b) => a.start - b.start);
  const parts = [];
  let pos = 0;
  sorted.forEach((s, i) => {
    const start = Math.max(s.start, pos);
    if (start > pos) parts.push(text.slice(pos, start));
    if (s.end > start) {
      parts.push(
        <mark key={i} ref={i === 0 ? firstRef : null}
              className={`ev${s.alt ? " alt" : ""}`}>
          {text.slice(start, s.end)}
        </mark>
      );
      pos = s.end;
    }
  });
  parts.push(text.slice(pos));
  return <pre className="srcpre">{parts}</pre>;
}

/** CSV as a grid; highlights are {row (1-based data row), col (header name)}. */
export function CsvGrid({ text, hits }) {
  const rows = useMemo(() => parseCSV(text), [text]);
  const key = JSON.stringify(hits);
  const firstRef = useScrollToHit(key);
  if (!rows.length) return <pre className="srcpre">{text}</pre>;
  const header = rows[0];
  let found = false;
  return (
    <table className="csvgrid">
      <thead>
        <tr>{header.map((h, i) => <th key={i}>{h}</th>)}</tr>
      </thead>
      <tbody>
        {rows.slice(1).map((r, ri) => (
          <tr key={ri}>
            {r.map((cell, ci) => {
              const hit = hits.some(
                (h) => h.row === ri + 1 && h.col === header[ci]
              );
              const ref = hit && !found ? ((found = true), firstRef) : null;
              return (
                <td key={ci} ref={ref} className={hit ? "hit" : ""}>
                  {cell}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Pretty-printed JSON with per-line path tracking; highlights are
    {path: "candidates[3].emailAddress"} — exact line match. */
export function JsonPane({ text, hits }) {
  const lines = useMemo(() => {
    try {
      const doc = JSON.parse(text);
      const out = [];
      walk(doc, "", 0, out, "");
      return out;
    } catch {
      return null;
    }
  }, [text]);
  const key = JSON.stringify(hits);
  const firstRef = useScrollToHit(key);
  if (!lines) return <pre className="srcpre">{text}</pre>;
  const paths = hits.map((h) => h.path);
  let found = false;
  return (
    <div>
      {lines.map((l, i) => {
        const hit = paths.includes(l.path);
        const ref = hit && !found ? ((found = true), firstRef) : null;
        return (
          <div key={i} ref={ref} className={`jsonline${hit ? " hit" : ""}`}>
            {"  ".repeat(l.indent)}
            {l.key != null && <span className="jsonkey">"{l.key}"</span>}
            {l.key != null && ": "}
            {l.open ? l.open :
              <span className={typeof l.value === "string" ? "jsonstr" : ""}>
                {JSON.stringify(l.value)}
              </span>}
            {l.comma && ","}
          </div>
        );
      })}
    </div>
  );
}

function walk(v, path, indent, out, keyLabel) {
  const base = { indent, key: keyLabel === "" ? null : keyLabel, path };
  if (Array.isArray(v)) {
    out.push({ ...base, open: "[" });
    v.forEach((el, i) =>
      walk(el, `${path}[${i}]`, indent + 1, out, "")
    );
    out.push({ indent, key: null, path, open: "]", comma: true });
  } else if (v !== null && typeof v === "object") {
    out.push({ ...base, open: "{" });
    Object.entries(v).forEach(([k, val]) =>
      walk(val, path ? `${path}.${k}` : k, indent + 1, out, k)
    );
    out.push({ indent, key: null, path, open: "}", comma: true });
  } else {
    out.push({ ...base, value: v, comma: true });
  }
}

/** A source the engine refused or could not read: the reason IS the content. */
export function SkippedPane({ source }) {
  return (
    <div>
      <div className="badge error" style={{ marginBottom: 8 }}>
        {source.status}
      </div>
      {(source.errors ?? []).map((e, i) => (
        <div key={i} className="body-medium" style={{ marginBottom: 6 }}>
          {e}
        </div>
      ))}
      <div className="body-small">
        This file degraded gracefully: the run continued, the reason is on
        record, and nothing was invented from unreadable bytes.
      </div>
    </div>
  );
}
