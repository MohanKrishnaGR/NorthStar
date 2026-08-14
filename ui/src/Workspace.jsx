import React, { useRef, useState } from "react";
import { loadBrowserEngine } from "./engine.js";
import { SourceIcon } from "./icons.jsx";
import { pressable } from "./lib.js";
import { SOURCE_ROWS, textToB64 } from "./samples.js";
import defaultConfig from "../../configs/default.json";
import recruiterViewConfig from "../../configs/recruiter_view.json";

const ACCEPT = ".csv,.json,.txt,.docx,.pdf";
const STATIC_CONFIGS = {
  default: defaultConfig,
  recruiter_view: recruiterViewConfig,
};

export default function Workspace({ serve, onBundle }) {
  const [engine, setEngine] = useState(null);
  const [engineStatus, setEngineStatus] = useState("");
  const [engineError, setEngineError] = useState(null);

  if (serve) {
    return <Workbench backend={serverBackend(serve)} onBundle={onBundle} />;
  }
  if (engine) {
    return <Workbench backend={browserBackend(engine)} onBundle={onBundle} />;
  }
  return (
    <div className="workspace-grid" style={{ gridTemplateColumns: "1fr" }}>
      <section className="card" style={{ maxWidth: 680, margin: "24px auto" }}>
        <div className="title-medium" style={{ marginBottom: 6 }}>
          Run the engine in your browser
        </div>
        <p className="body-medium">
          This is a static page, but the pipeline itself is portable: the
          <b> real engine</b> — the exact wheel this repo builds, deterministic
          merge, provenance, confidence and all — can load right here via
          WebAssembly. Your files are processed <b>inside this tab</b> and
          never leave your machine: for candidate data, that is a stronger
          privacy posture than uploading to any demo server.
        </p>
        <p className="body-small">
          One-time download ≈ 15–20 MB (Pyodide runtime + packages). Prefer a
          local run? <code>python -m transformer serve</code> gives the same
          workspace against a native engine.
        </p>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 10 }}>
          <button className="btn filled" disabled={!!engineStatus}
                  onClick={async () => {
                    setEngineError(null);
                    try {
                      setEngine(await loadBrowserEngine(setEngineStatus));
                    } catch (e) {
                      setEngineStatus("");
                      setEngineError(String(e));
                    }
                  }}>
            {engineStatus ? "loading…" : "⬇ load in-browser engine"}
          </button>
          <span className="body-small">{engineStatus}</span>
        </div>
        {engineError && (
          <div className="refusal" style={{ marginTop: 10 }}>{engineError}</div>
        )}
      </section>
    </div>
  );
}

function serverBackend(serve) {
  return {
    kind: "server",
    banner: null,
    configs: serve.configs,
    canonicalTypes: serve.canonical_types,
    samples: serve.samples,
    async run(payload) {
      const resp = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw body.errors ?? ["run failed"];
      return body;
    },
  };
}

function browserBackend(engine) {
  return {
    kind: "browser",
    banner: `in-browser engine v${engine.engine_version} · scoring `
      + `${engine.scoring_version} · files never leave this tab`
      + (engine.resumeSupport ? "" : " · docx/pdf extras unavailable (those sources will be skipped with a reason)"),
    configs: STATIC_CONFIGS,
    canonicalTypes: engine.canonical_types,
    samples: [],
    run: (payload) => engine.run(payload),
  };
}

function Workbench({ backend, onBundle }) {
  const [files, setFiles] = useState([]); // {name, size, b64}
  const [preset, setPreset] = useState("default");
  const [configText, setConfigText] = useState(
    JSON.stringify(backend.configs.default, null, 2)
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

  const stageTemplates = (rows) => {
    setFiles((cur) => {
      let next = [...cur];
      rows.forEach(({ template }) => {
        next = [
          ...next.filter((x) => x.name !== template.name),
          { name: template.name, size: template.content.length,
            b64: textToB64(template.content) },
        ];
      });
      return next;
    });
  };

  const pickPreset = (name) => {
    setPreset(name);
    if (backend.configs[name]) {
      setConfigText(JSON.stringify(backend.configs[name], null, 2));
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
      cfg.fields.push({
        path: path.replace(/[[\]().]/g, "_").replace(/_+$/, ""),
        from: path, type: backend.canonicalTypes[path],
      });
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
      setErrors(["stage at least one source file" +
                 (backend.samples.length ? ", or load a sample corpus" : "")]);
      return;
    }
    setRunning(true);
    try {
      const bundle = await backend.run({
        files: sample ? undefined : files.map(({ name, b64 }) => ({ name, b64 })),
        sample: sample ?? undefined,
        config,
        as_of: asOf || null,
        default_region: region || null,
      });
      onBundle(bundle);
    } catch (e) {
      setErrors(Array.isArray(e) ? e : [String(e)]);
    } finally {
      setRunning(false);
    }
  };

  const cfgObj = safeParse(configText);

  return (
    <div style={{ overflow: "auto" }}>
      {backend.banner && (
        <div style={{ maxWidth: 1240, margin: "14px auto -8px", padding: "0 26px" }}>
          <span className="chip tonal">{backend.banner}</span>
        </div>
      )}
      <div className="workspace-grid">
        <section>
          <div className="title-medium" style={{ marginBottom: 4 }}>Sources</div>
          <div className="body-small" style={{ marginBottom: 10 }}>
            All six source types from the problem statement land here — drop
            the files, the adapters detect the rest.
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
          {backend.samples.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <span className="label">or load a sample corpus</span>
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                {backend.samples.map((s) => (
                  <button key={s} className="btn tonal" disabled={running}
                          onClick={() => run(s)}>
                    ▶ {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          <details style={{ marginTop: 14 }}>
            <summary className="body-small" style={{ cursor: "pointer" }}>
              what belongs here? (all six source types — with sample templates)
            </summary>
            <div className="body-small" style={{ margin: "8px 0 4px" }}>
              The samples are one coherent person, Sam Okafor — stage several,
              hit run, and watch the sources merge into one profile.
              <button className="textbtn" style={{ marginLeft: 8 }}
                      onClick={() => stageTemplates(
                        SOURCE_ROWS.filter((r) => r.template))}>
                ⤓ stage all samples
              </button>
            </div>
            <table className="hints">
              <tbody>
                {SOURCE_ROWS.map((row) => (
                  <tr key={row.pattern}>
                    <td className="srcicon"><SourceIcon kind={row.icon} /></td>
                    <td><code>{row.pattern}</code></td>
                    <td className="body-small">{row.why}</td>
                    <td>
                      {row.template && (
                        <button className="textbtn"
                                title={`stage ${row.template.name}`}
                                onClick={() => stageTemplates([row])}>
                          use sample
                        </button>
                      )}
                    </td>
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
            {Object.keys(backend.configs).map((name) => (
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
              {Object.keys(backend.canonicalTypes).map((p) => (
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
    </div>
  );
}

function safeParse(s) {
  try { return JSON.parse(s); } catch { return null; }
}
