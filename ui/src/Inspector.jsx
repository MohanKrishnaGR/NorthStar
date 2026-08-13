import React from "react";
import { SOURCE_ICONS, pct, stable } from "./lib.js";

/** The "show the math" panel: winner, alternatives, atoms, arithmetic. */
export default function Inspector({ cand, sel, entry, onJump, onClose }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="title-small">
          {sel.key}
          {sel.el != null && entry.kind === "set"
            ? ` · ${JSON.stringify(entry.elements[sel.el]?.value)}` : ""}
        </span>
        <span className="spacer" style={{ flex: 1 }} />
        <button className="textbtn" onClick={onClose}>close</button>
      </div>
      {entry.kind === "scalar" && <Scalar entry={entry} onJump={onJump} />}
      {entry.kind === "set" && <SetEntry entry={entry} el={sel.el} onJump={onJump} />}
      {entry.kind === "entry" && <MergedEntry entry={entry} onJump={onJump} />}
    </div>
  );
}

function AtomsTable({ atoms, winnerRepr, onJump }) {
  return (
    <table className="atoms">
      <thead>
        <tr>
          <th>source</th><th>method</th><th>raw</th>
          <th>strength</th><th></th>
        </tr>
      </thead>
      <tbody>
        {atoms.map((a, i) => {
          const isAlt = winnerRepr != null && stable(a.value) !== winnerRepr;
          return (
            <tr key={i} style={isAlt ? { opacity: 0.72 } : null}>
              <td>
                <span className="chip">
                  {SOURCE_ICONS[a.source_type] ?? "•"} {a.source_id}
                </span>
                {isAlt && <span className="badge warn" style={{ marginLeft: 6 }}>
                  lost: {JSON.stringify(a.value)}</span>}
              </td>
              <td><code>{a.method}</code></td>
              <td style={{ maxWidth: 260, overflowWrap: "anywhere" }}>
                {a.raw ?? "—"}
              </td>
              <td><code>{a.strength}</code></td>
              <td>
                {a.locator && (
                  <button className="textbtn"
                          onClick={() => onJump(a.source_id)}>
                    ground ↗
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function MathScalar({ trace }) {
  const s = Object.entries(trace.per_source ?? {});
  const prod = s.map(([, v]) => `(1−${v})`).join("·") || "1";
  const winSum = s.reduce((acc, [, v]) => acc + v, 0);
  return (
    <div className="mathbox">
      {s.map(([src, v]) => `s(${src}) = ${v}`).join("\n")}
      {"\n"}agreement = 1 − {prod} = {trace.agreement}
      {"\n"}support   = {round6(winSum)} / {trace.competing_total} = {trace.support}
      {"\n"}confidence = {trace.agreement} × {trace.support} = <b>{trace.confidence}</b>
    </div>
  );
}

function MathElement({ atoms, confidence }) {
  const perSource = {};
  atoms.forEach((a) => {
    perSource[a.source_id] = Math.max(perSource[a.source_id] ?? 0, a.strength);
  });
  const s = Object.entries(perSource);
  const prod = s.map(([, v]) => `(1−${v})`).join("·") || "1";
  return (
    <div className="mathbox">
      {s.map(([src, v]) => `s(${src}) = ${v}`).join("\n")}
      {"\n"}confidence = 1 − {prod} = <b>{confidence}</b>
      {"\n"}(set element: absence in a source is not contradiction — no
      support penalty)
    </div>
  );
}

function Scalar({ entry, onJump }) {
  const winnerRepr = stable(entry.winner);
  const alts = [...new Set(
    entry.atoms.filter((a) => stable(a.value) !== winnerRepr)
      .map((a) => JSON.stringify(a.value))
  )];
  return (
    <div>
      <div className="body-medium" style={{ marginTop: 4 }}>
        winner: <b>{JSON.stringify(entry.winner)}</b>
        {alts.length > 0 && (
          <span className="altstack">
            {" "}· overruled:{" "}
            {alts.map((a) => <span key={a} className="alt">{a} </span>)}
          </span>
        )}
      </div>
      <AtomsTable atoms={entry.atoms} winnerRepr={winnerRepr} onJump={onJump} />
      <MathScalar trace={entry.trace} />
    </div>
  );
}

function SetEntry({ entry, el, onJump }) {
  if (el == null) {
    return (
      <div className="body-small" style={{ marginTop: 6 }}>
        {entry.elements.length} elements — select one in the profile to audit it.
      </div>
    );
  }
  const e = entry.elements[el];
  if (!e) return null;
  return (
    <div>
      <AtomsTable atoms={e.atoms} winnerRepr={null} onJump={onJump} />
      <MathElement atoms={e.atoms} confidence={e.confidence} />
    </div>
  );
}

function MergedEntry({ entry, onJump }) {
  return (
    <div>
      <div className="body-small" style={{ margin: "4px 0" }}>
        merged from {entry.atoms.length} evidence atom
        {entry.atoms.length === 1 ? "" : "s"} · entry confidence{" "}
        {pct(entry.confidence)}
      </div>
      <AtomsTable atoms={entry.atoms} winnerRepr={null} onJump={onJump} />
      <MathElement atoms={entry.atoms} confidence={entry.confidence} />
    </div>
  );
}

const round6 = (x) => Math.round(x * 1e6) / 1e6;
