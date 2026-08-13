import React, { useMemo, useState } from "react";
import CandidateView from "./CandidateView.jsx";
import { clusterSourceIds, pct, pressable } from "./lib.js";

export default function App({ bundle }) {
  const [candId, setCandId] = useState(null);
  const cand = useMemo(
    () => bundle.candidates.find((c) => c.candidate_id === candId) ?? null,
    [bundle, candId]
  );

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <header className="appbar">
        <div className="brand" {...pressable(() => setCandId(null))}
             title="Back to all candidates">
          <div className="logo">Cx</div>
          <div>
            <div className="title-medium">Candidate Explorer</div>
            <div className="body-small">
              every value traceable · every score auditable
            </div>
          </div>
        </div>
        <div className="spacer" />
        {cand && (
          <button className="textbtn" onClick={() => setCandId(null)}>
            ← all candidates
          </button>
        )}
        <span className="chip">as-of {bundle.run.as_of ?? "—"}</span>
        <span className="chip">{bundle.run.profiles} profiles</span>
        <span className="chip">{bundle.sources.length} sources</span>
      </header>
      {cand ? (
        <CandidateView bundle={bundle} cand={cand} />
      ) : (
        <BatchView bundle={bundle} onOpen={setCandId} />
      )}
    </div>
  );
}

function BatchView({ bundle, onOpen }) {
  const sorted = [...bundle.candidates].sort(
    (a, b) =>
      (b.canonical.overall_confidence ?? 0) -
      (a.canonical.overall_confidence ?? 0)
  );
  return (
    <div style={{ overflow: "auto" }}>
      <div className="batch">
        {sorted.map((c) => (
          <CandidateCard key={c.candidate_id} cand={c}
                         onOpen={() => onOpen(c.candidate_id)} />
        ))}
      </div>
    </div>
  );
}

function CandidateCard({ cand, onOpen }) {
  const p = cand.canonical;
  const overall = p.overall_confidence ?? 0;
  const flags = cand.cluster.flags ?? [];
  const softKey = (cand.cluster.match_keys_used ?? []).some((k) =>
    k.startsWith("soft:")
  );
  return (
    <div className="card clickable" {...pressable(onOpen)}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="title-medium" style={{ flex: 1, minWidth: 0 }}>
          {p.full_name ?? <i>(unnamed)</i>}
        </span>
        <span className="conftag">{pct(overall)}</span>
      </div>
      <div className="confbar" style={{ margin: "8px 0 10px" }}>
        <div style={{ width: pct(overall) }} />
      </div>
      <div className="body-small" style={{ marginBottom: 8 }}>
        {p.emails[0] ?? "no email"} · {p.headline ?? "no headline"}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span className="chip">
          {cand.cluster.record_ids.length} record
          {cand.cluster.record_ids.length === 1 ? "" : "s"} ·{" "}
          {clusterSourceIds(cand).length} source
          {clusterSourceIds(cand).length === 1 ? "" : "s"}
        </span>
        {flags.map((f) => (
          <span key={f} className="badge warn">{f}</span>
        ))}
        {softKey && <span className="badge warn">soft-key merge</span>}
        {cand.excluded && <span className="badge error">excluded by config</span>}
      </div>
    </div>
  );
}
