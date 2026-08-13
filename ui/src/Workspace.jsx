import React, { useRef, useState } from "react";
import { pressable } from "./lib.js";

const ACCEPT = ".csv,.json,.txt,.docx,.pdf";

const SOURCE_HINTS = [
  ["recruiters.csv", "Recruiter CSV export — rows of name/email/phone/company/title"],
  ["ats.json", "ATS JSON blob — its own field names, mapped by the adapter"],
  ["notes_*.txt", "Recruiter notes — free text, rule-extracted"],
  ["resume_*.docx / *.pdf", "Resumes — text extracted, then same rules as notes"],
  ["github_<login>.json", "GitHub profile — recorded API payload (live fetch is descoped: determinism, ADR-002/017)"],
  ["linkedin_<slug>.json", "LinkedIn profile — recorded export payload (no sanctioned live API)"],
];

export default function Workspace({ serve, onBundle }) {
  const [files, setFiles] = useState([]); // {name, size, b64}
  const [preset, setPreset] = useState("default");
  const [configText, setConfigText] = useState(
    JSON.stringify(serve.configs.default, null, 2)
  );
  const [asOf, setAsOf] = useState("");
  const [region, setRegion] = useState("");
  const [running, setRunning] = useState(false);
  const [errors, setErrors] = useState([]);
  const inputRef = useRef(null);

  const stage = (fileList) => {
    [...fileList].forEach((f) => {
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = String(reader.result).split(",", 2)[1] ?? "";
        setFiles((cur) => [
          ...cur.filter((x) => x.name !== f.name),
          { name: f.name, size: f.size, b64 },
        ]);
      };
      reader.readAsDataURL(f);
    });
  };

  const pickPreset = (name) => {
    setPreset(name);
    if (serve.configs[name]) {
      setConfigText(JSON.stringify(serve.configs[name], null, 2));
    }
  };

  const patchConfig = (fn) => {
    try {
      const cfg = JSON.parse(configText);
      fn(cfg);
      setConfigText(JSON.stringify(cfg, null, 2));
      setPreset("custom");
    } catch {
      setErrors(["config editor does not contain valid JSON"]);
    }
  };

  const addFieldTemplate = (path) => {
    patchConfig((cfg) => {
      cfg.fields = cfg.fields ?? [];
      cfg.fields.push({ path: path.replace(/[[\]().]/g, "_").replace(/_+$/, ""),
                        from: path, type: serve.canonical_types[path] });
    });
  };

  const run = async (sample = null) => {
    setErrors([]);
    let config;
    try {
      config = JSON.parse(configText);
    } catch (e) {
      setErrors([`config editor: ${e.message}`]);
      return;
    }
    if (!sample && !files.length) {
      setErrors(["stage at least one source file, or load a sample corpus"]);
      return;
    }
    setRunning(true);
    try {
      const resp = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          files: sample ? undefined : files.map(({ name, b64 }) => ({ name, b64 })),
          sample: sample ?? undefined,
          config,
          as_of: asOf || null,
          default_region: region || null,
        }),
      });
      const body = await resp.json();
      if (!resp.ok) setErrors(body.errors ?? ["run failed"]);
      else onBundle(body);
    } catch (e) {
      setErrors([`server unreachable: ${e.message}`]);
    } finally {
      setRunning(false);
    }
  };

  const cfgObj = safeParse(configText);

  return (
    <div className="workspace-grid">
      <section>
        <div className="title-medium" style={{ marginBottom: 4 }}>Sources</div>
        <div className="body-small" style={{ marginBottom: 10 }}>
          All six source types from the problem statement land here — drop the
          files, the adapters detect the rest.
        </div>
        <div className="dropzone"
             {...pressable(() => inputRef.current?.click())}
             onDragOver={(e) => e.preventDefault()}
             onDrop={(e) => { e.preventDefault(); stage(e.dataTransfer.files); }}>
          drop source files here — or click to browse
          <div className="body-small">csv · json · txt · docx · pdf</div>
          <input ref={inputRef} type="file" multiple accept={ACCEPT}
                 style={{ display: "none" }}
                 onChange={(e) => { stage(e.target.files); e.target.value = ""; }} />
        </div>
        {files.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {files.map((f) => (
              <div key={f.name} className="stagedfile">
                <span style={{ flex: 1 }}>{f.name}</span>
                <span className="body-small">{(f.size / 1024).toFixed(1)} KB</span>
                <button className="textbtn"
                        onClick={() =>
                          setFiles((cur) => cur.filter((x) => x.name !== f.name))
                        }>remove</button>
              </div>
            ))}
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <span className="label">or load a sample corpus</span>
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            {serve.samples.map((s) => (
              <button key={s} className="btn tonal" disabled={running}
                      onClick={() => run(s)}>
                ▶ {s}
              </button>
            ))}
          </div>
        </div>
        <details style={{ marginTop: 14 }}>
          <summary className="body-small" style={{ cursor: "pointer" }}>
            what belongs here? (all six source types)
          </summary>
          <table className="hints">
            <tbody>
              {SOURCE_HINTS.map(([pat, why]) => (
                <tr key={pat}>
                  <td><code>{pat}</code></td>
                  <td className="body-small">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section>
        <div className="title-medium" style={{ marginBottom: 4 }}>
          Output config
        </div>
        <div className="body-small" style={{ marginBottom: 10 }}>
          The runtime projection config — same engine, no code changes. Bad
          configs fail at load with every error listed, before any candidate
          is processed.
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          {Object.keys(serve.configs).map((name) => (
            <button key={name}
                    className={`btn${preset === name ? " tonal" : ""}`}
                    onClick={() => pickPreset(name)}>
              {name}
            </button>
          ))}
          {preset === "custom" && <span className="chip">custom</span>}
        </div>
        <textarea className="cfgedit" spellCheck={false} value={configText}
                  onChange={(e) => { setConfigText(e.target.value); setPreset("custom"); }} />
        {cfgObj && (
          <div style={{ display: "flex", gap: 10, alignItems: "center",
                        flexWrap: "wrap", marginTop: 8 }}>
            <label className="chip">
              <input type="checkbox" checked={!!cfgObj.include_provenance}
                     onChange={(e) => patchConfig((c) => {
                       c.include_provenance = e.target.checked;
                     })} /> provenance
            </label>
            <label className="chip">
              <input type="checkbox" checked={!!cfgObj.include_confidence}
                     onChange={(e) => patchConfig((c) => {
                       c.include_confidence = e.target.checked;
                     })} /> confidence
            </label>
            <span className="chip">
              on&nbsp;missing:&nbsp;
              <select value={cfgObj.on_missing ?? "null"}
                      onChange={(e) => patchConfig((c) => {
                        c.on_missing = e.target.value;
                      })}>
                <option>null</option><option>omit</option><option>error</option>
              </select>
            </span>
          </div>
        )}
        <details style={{ marginTop: 10 }}>
          <summary className="body-small" style={{ cursor: "pointer" }}>
            add a field from a canonical path
          </summary>
          <div style={{ marginTop: 6 }}>
            {Object.keys(serve.canonical_types).map((p) => (
              <button key={p} className="pathchip"
                      onClick={() => addFieldTemplate(p)}>{p}</button>
            ))}
          </div>
        </details>

        <div className="runbar">
          <label className="chip">as-of&nbsp;
            <input value={asOf} placeholder="YYYY-MM" size={7}
                   onChange={(e) => setAsOf(e.target.value)} />
          </label>
          <label className="chip">default region&nbsp;
            <input value={region} placeholder="e.g. IN" size={4}
                   onChange={(e) => setRegion(e.target.value.toUpperCase())} />
          </label>
          <span style={{ flex: 1 }} />
          <button className="btn filled" disabled={running}
                  onClick={() => run(null)}>
            {running ? "running…" : "▶ run pipeline"}
          </button>
        </div>
        {errors.length > 0 && (
          <div className="refusal" style={{ marginTop: 10 }}>
            {errors.map((e, i) => <div key={i}>{e}</div>)}
          </div>
        )}
      </section>
    </div>
  );
}

function safeParse(s) {
  try { return JSON.parse(s); } catch { return null; }
}
