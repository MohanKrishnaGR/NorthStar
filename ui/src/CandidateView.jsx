import React, { useEffect, useMemo, useState } from "react";
import Inspector from "./Inspector.jsx";
import { SourceIcon } from "./icons.jsx";
import { CsvGrid, JsonPane, SkippedPane, TextPane } from "./renderers.jsx";
import {
  atomsFor, clusterSourceIds, emptyReasons, pct, pressable,
  refusalsTouching, sourceOf, stable,
} from "./lib.js";

export default function CandidateView({ bundle, cand }) {
  const [sel, setSel] = useState(null); // {key, el?}
  const srcIds = clusterSourceIds(cand);
  const sources = bundle.sources.filter((s) => srcIds.includes(s.source_id));
  const [activeSrc, setActiveSrc] = useState(sources[0]?.source_id ?? null);

  const selAtoms = useMemo(
    () => (sel ? atomsFor(cand, sel) : []),
    [cand, sel]
  );

  // Grounding: when a field is selected, front a source that actually
  // contains evidence for it.
  useEffect(() => {
    if (!sel || !selAtoms.length) return;
    if (!selAtoms.some((a) => a.source_id === activeSrc)) {
      setActiveSrc(selAtoms[0].source_id);
    }
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps

  const entry = sel ? cand.debug[sel.key] : null;
  const winnerRepr = entry?.kind === "scalar" ? stable(entry.winner) : null;
  const activeAtoms = selAtoms.filter((a) => a.source_id === activeSrc);
  const activeSource = sources.find((s) => s.source_id === activeSrc);

  const toggle = (key, el = null) =>
    setSel((cur) =>
      cur && cur.key === key && cur.el === el ? null : { key, el }
    );

  return (
    <div className="workbench">
      <section className="dock">
        <div className="dock-tabs">
          {sources.map((s) => (
            <button key={s.source_id}
                    className={`dock-tab${s.source_id === activeSrc ? " active" : ""}`}
                    onClick={() => setActiveSrc(s.source_id)}>
              <span className="srcicon"><SourceIcon kind={s.source_type} size={14} /></span>
              {s.source_id}
              <span className={`srcstatus-${s.status}`}>●</span>
            </button>
          ))}
        </div>
        <div className="dock-body">
          {activeSource ? (
            <SourceBody source={activeSource} atoms={activeAtoms}
                        winnerRepr={winnerRepr} />
          ) : (
            <div className="body-small">no sources in this cluster</div>
          )}
        </div>
      </section>

      <section className="rightcol">
        <div className="profile-scroll">
          <ProfileCard bundle={bundle} cand={cand} sel={sel} toggle={toggle} />
          <IdentityPanel bundle={bundle} cand={cand} />
        </div>
        {sel && entry && (
          <div className="inspector">
            <Inspector cand={cand} sel={sel} entry={entry}
                       onJump={(sid) => setActiveSrc(sid)}
                       onClose={() => setSel(null)} />
          </div>
        )}
      </section>
    </div>
  );
}

function SourceBody({ source, atoms, winnerRepr }) {
  if (source.status === "skipped" || !source.content) {
    return <SkippedPane source={source} />;
  }
  const { kind, text } = source.content;
  const mark = atoms
    .filter((a) => a.locator)
    .map((a) => ({
      ...a.locator,
      alt: winnerRepr != null && stable(a.value) !== winnerRepr,
    }));
  if (kind === "csv") {
    return <CsvGrid text={text} hits={mark.filter((m) => m.kind === "cell")} />;
  }
  if (kind === "json") {
    return <JsonPane text={text} hits={mark.filter((m) => m.kind === "path")} />;
  }
  return <TextPane text={text} spans={mark.filter((m) => m.kind === "span")} />;
}

function Row({ label, value, fieldKey, el = null, conf, sel, toggle, empty }) {
  const isSel = sel && sel.key === fieldKey && sel.el === el;
  return (
    <div className={`fieldrow${isSel ? " selected" : ""}`}
         {...pressable(() => toggle(fieldKey, el))}
         aria-pressed={!!isSel}>
      <span className="k label">{label}</span>
      <span className="v">
        {value ?? <span className="empty">{empty ?? "— no evidence"}</span>}
      </span>
      {conf != null && <span className="conftag">{pct(conf)}</span>}
    </div>
  );
}

function ProfileCard({ bundle, cand, sel, toggle }) {
  const p = cand.canonical;
  const fc = p.field_confidence ?? {};
  const phoneWhy = emptyReasons(bundle, cand, "phones")
    .map((u) => `${u.reason}: ${u.raw_value}`).join("; ");

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span className="headline-small">
          {p.full_name ?? <i>(unnamed)</i>}
        </span>
        <span className="chip primary">overall {pct(p.overall_confidence)}</span>
        {cand.excluded && (
          <span className="badge error">excluded by this config</span>
        )}
      </div>

      <div className="section"><span className="label">identity</span></div>
      <Row label="name" value={p.full_name} fieldKey="full_name"
           conf={fc.full_name} sel={sel} toggle={toggle} />
      {p.emails.length ? (
        p.emails.map((e, i) => (
          <Row key={e} label={i === 0 ? "emails" : ""} value={e}
               fieldKey="emails" el={i}
               conf={cand.debug.emails?.elements[i]?.confidence}
               sel={sel} toggle={toggle} />
        ))
      ) : (
        <Row label="emails" value={null} fieldKey="emails" sel={sel}
             toggle={toggle} />
      )}
      {p.phones.length ? (
        p.phones.map((ph, i) => (
          <Row key={ph} label={i === 0 ? "phones" : ""} value={ph}
               fieldKey="phones" el={i}
               conf={cand.debug.phones?.elements[i]?.confidence}
               sel={sel} toggle={toggle} />
        ))
      ) : (
        <Row label="phones" value={null} fieldKey="phones" sel={sel}
             toggle={toggle}
             empty={phoneWhy ? `— withheld (${phoneWhy})` : "— no evidence"} />
      )}

      <div className="section"><span className="label">about</span></div>
      <Row label="headline" value={p.headline} fieldKey="headline"
           conf={fc.headline} sel={sel} toggle={toggle} />
      <Row label="location" fieldKey="location" conf={fc.location}
           value={p.location
             ? [p.location.city, p.location.region, p.location.country]
                 .filter(Boolean).join(", ")
             : null}
           sel={sel} toggle={toggle} />
      <Row label="years exp" value={p.years_experience} fieldKey="years_experience"
           conf={fc.years_experience} sel={sel} toggle={toggle} />
      {["linkedin", "github", "portfolio"].map((b) => (
        <Row key={b} label={b} value={p.links[b]} fieldKey={`links.${b}`}
             conf={cand.debug[`links.${b}`]?.trace?.confidence}
             sel={sel} toggle={toggle} />
      ))}
      {p.links.other.map((u, i) => (
        <Row key={u} label={i === 0 ? "other links" : ""} value={u}
             fieldKey="links.other" el={i} sel={sel} toggle={toggle} />
      ))}

      <div className="section"><span className="label">
        skills ({p.skills.length})</span></div>
      <div>
        {p.skills.map((s, i) => {
          const isSel = sel && sel.key === "skills" && sel.el === i;
          return (
            <span key={s.name}
                  className={`skillchip${isSel ? " selected" : ""}`}
                  {...pressable(() => toggle("skills", i))}
                  title={s.canonical ? "canonical" : "unknown skill — kept verbatim, flagged"}>
              {s.name}
              {!s.canonical && <span className="noncanon">?</span>}
              <span className="conf">{pct(s.confidence)}</span>
            </span>
          );
        })}
        {!p.skills.length && <span className="body-small">— none extracted</span>}
      </div>

      <div className="section"><span className="label">experience</span></div>
      {p.experience.map((e, i) => {
        const isSel = sel && sel.key === `experience[${i}]`;
        return (
          <div key={i} className={`fieldrow${isSel ? " selected" : ""}`}
               {...pressable(() => toggle(`experience[${i}]`))}>
            <span className="v">
              <b>{e.title ?? "—"}</b> · {e.company ?? "—"}
              <span className="body-small" style={{ marginLeft: 8 }}>
                {e.start ?? "?"} → {e.is_current ? "present" : e.end ?? "?"}
              </span>
            </span>
            <span className="conftag">
              {pct(cand.debug[`experience[${i}]`]?.confidence)}
            </span>
          </div>
        );
      })}
      {!p.experience.length && (
        <div className="body-small" style={{ padding: "0 8px" }}>— none</div>
      )}

      <div className="section"><span className="label">education</span></div>
      {p.education.map((e, i) => {
        const isSel = sel && sel.key === `education[${i}]`;
        return (
          <div key={i} className={`fieldrow${isSel ? " selected" : ""}`}
               {...pressable(() => toggle(`education[${i}]`))}>
            <span className="v">
              <b>{e.institution ?? "—"}</b> · {e.degree ?? "—"}{" "}
              {e.field ? `· ${e.field}` : ""}
              <span className="body-small" style={{ marginLeft: 8 }}>
                {e.end_year ?? ""}
              </span>
            </span>
            <span className="conftag">
              {pct(cand.debug[`education[${i}]`]?.confidence)}
            </span>
          </div>
        );
      })}
      {!p.education.length && (
        <div className="body-small" style={{ padding: "0 8px" }}>— none</div>
      )}
    </div>
  );
}

function IdentityPanel({ bundle, cand }) {
  const refusals = refusalsTouching(bundle, cand);
  return (
    <div className="card idgraph" style={{ margin: "18px 0 8px" }}>
      <div className="title-small" style={{ marginBottom: 6 }}>
        identity cluster
      </div>
      {cand.cluster.record_ids.map((rid) => (
        <div key={rid} className="rec">
          <span className="chip">{sourceOf(rid)}</span>
          <span className="body-small">{rid.split("#")[1]}</span>
        </div>
      ))}
      <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
        {cand.cluster.match_keys_used.map((k) => (
          <span key={k} className="chip tonal keyedge">{k}</span>
        ))}
        {!cand.cluster.match_keys_used.length && (
          <span className="body-small">single record — no joins needed</span>
        )}
        {cand.cluster.flags.map((f) => (
          <span key={f} className="badge warn">{f}</span>
        ))}
      </div>
      {refusals.map((r, i) => (
        <div key={i} className="refusal">
          refused union on <b>{r.key}</b> — {r.reason} (the guard would not
          fuse incompatible names; see {r.records.join(" vs ")})
        </div>
      ))}
    </div>
  );
}
