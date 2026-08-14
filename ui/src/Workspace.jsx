import React, { useEffect, useMemo, useRef, useState } from "react";
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
  // Corpora published next to the page (Pages ships goldens/t1 + a manifest)
  // so the in-browser engine gets the same "▶ goldens/t1" button as serve
  // mode. Absent manifest (e.g. a file:// explorer.html) ⇒ no button.
  const [corpora, setCorpora] = useState({});
  useEffect(() => {
    if (serve) return; // serve mode: the server lists its own samples
    fetch(new URL("./goldens/t1/manifest.json", window.location))
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => {
        if (m && Array.isArray(m.files)) setCorpora({ "goldens/t1": m.files });
      })
      .catch(() => {});
  }, [serve]);

  if (serve) {
    return <Workbench backend={serverBackend(serve)} onBundle={onBundle} />;
  }
  if (engine) {
    return <Workbench backend={browserBackend(engine, corpora)}
                      onBundle={onBundle} />;
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
    async fetchSample(name) {
      const resp = await fetch(`/api/sample?name=${encodeURIComponent(name)}`);
      const body = await resp.json();
      if (!resp.ok) throw body.errors ?? ["sample fetch failed"];
      return body.files;
    },
    async extractText(payload) {
      const resp = await fetch("/api/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw body.errors ?? ["extraction failed"];
      return body.text;
    },
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

function browserBackend(engine, corpora) {
  return {
    kind: "browser",
    banner: `in-browser engine v${engine.engine_version} · scoring `
      + `${engine.scoring_version} · files never leave this tab`
      + (engine.resumeSupport ? "" : " · docx/pdf extras unavailable (those sources will be skipped with a reason)"),
    configs: STATIC_CONFIGS,
    canonicalTypes: engine.canonical_types,
    samples: Object.keys(corpora),
    // Fetch the published corpus files so the UI can stage them like drops.
    fetchSample(name) {
      return Promise.all(corpora[name].map(async (fname) => {
        const resp = await fetch(new URL(`./${name}/${fname}`, window.location));
        if (!resp.ok) throw [`${name}/${fname}: fetch failed (${resp.status})`];
        const bytes = new Uint8Array(await resp.arrayBuffer());
        return { name: fname, size: bytes.length, b64: bytesToB64(bytes) };
      }));
    },
    extractText: (payload) => engine.extractText(payload),
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
  const [staging, setStaging] = useState(false);
  const [errors, setErrors] = useState([]);
  const [previewName, setPreviewName] = useState(null); // staged file open below
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

  // Stage a corpus; running stays the user's explicit ▶, with their config.
  const stageSample = async (name) => {
    setErrors([]);
    setStaging(true);
    try {
      const fetched = await backend.fetchSample(name);
      setFiles((cur) => {
        let next = [...cur];
        fetched.forEach((f) => {
          next = [...next.filter((x) => x.name !== f.name), f];
        });
        return next;
      });
    } catch (e) {
      setErrors(Array.isArray(e) ? e : [String(e)]);
    } finally {
      setStaging(false);
    }
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

  const run = async () => {
    setErrors([]);
    let config;
    try {
      config = JSON.parse(configText);
    } catch (e) {
      setErrors([`config editor: ${e.message}`]);
      return;
    }
    if (!files.length) {
      setErrors(["stage at least one source file" +
                 (backend.samples.length ? ", or stage a sample corpus" : "")]);
      return;
    }
    setRunning(true);
    try {
      const bundle = await backend.run({
        files: files.map(({ name, b64 }) => ({ name, b64 })),
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
                <React.Fragment key={f.name}>
                  <div className="stagedfile">
                    <span className="fname" title="click to preview"
                          {...pressable(() => setPreviewName(
                            (cur) => (cur === f.name ? null : f.name)))}>
                      {f.name}
                    </span>
                    <span className="body-small">{(f.size / 1024).toFixed(1)} KB</span>
                    <button className="textbtn"
                            onClick={() => setPreviewName(
                              (cur) => (cur === f.name ? null : f.name))}>
                      {previewName === f.name ? "close" : "preview"}
                    </button>
                    <button className="textbtn"
                            onClick={() => {
                              setFiles((cur) => cur.filter((x) => x.name !== f.name));
                              setPreviewName((cur) => (cur === f.name ? null : cur));
                            }}>remove</button>
                  </div>
                  {previewName === f.name &&
                    <FilePreview file={f} backend={backend} />}
                </React.Fragment>
              ))}
            </div>
          )}
          {backend.samples.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <span className="label">or stage a sample corpus</span>
              <div style={{ display: "flex", gap: 8, alignItems: "center",
                            marginTop: 6 }}>
                {backend.samples.map((s) => (
                  <button key={s} className="btn tonal" disabled={staging}
                          onClick={() => stageSample(s)}>
                    ⤓ {s}
                  </button>
                ))}
                <span className="body-small">
                  {staging ? "fetching corpus…"
                    : "files land above — review, then ▶ run pipeline"}
                </span>
              </div>
            </div>
          )}
          <details open style={{ marginTop: 14 }}>
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
                    onClick={() => run()}>
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

/* ---- staged-file preview ---------------------------------------------- */

const PREVIEW_TEXT_CAP = 20000; // chars shown for text formats
const PREVIEW_ROW_CAP = 30;     // data rows shown for CSV

function FilePreview({ file, backend }) {
  const ext = file.name.toLowerCase().split(".").pop();
  const isBinary = ext === "docx" || ext === "pdf";
  // docx/pdf go through the engine's own extractor (async), so the preview
  // is the exact prose the pipeline will scan — not a second parser.
  const [extracted, setExtracted] = useState(null);
  useEffect(() => {
    if (!isBinary) return undefined;
    let live = true;
    setExtracted({ status: "loading" });
    backend.extractText({ name: file.name, b64: file.b64 })
      .then((text) => { if (live) setExtracted({ status: "ok", text }); })
      .catch((e) => {
        if (live) {
          setExtracted({ status: "err",
                         errors: Array.isArray(e) ? e : [String(e)] });
        }
      });
    return () => { live = false; };
  }, [file, backend, isBinary]);

  const view = useMemo(
    () => (isBinary ? extractedView(ext, extracted) : buildPreview(file)),
    [file, isBinary, ext, extracted]);
  return (
    <div className="filepreview">
      {view.kind === "table" ? (
        <div style={{ overflowX: "auto" }}>
          <table className="preview">
            <thead>
              <tr>{view.head.map((h, i) => <th key={i}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {view.body.map((row, i) => (
                <tr key={i}>{row.map((c, j) => <td key={j}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : view.kind === "text" ? (
        <pre>{view.text}</pre>
      ) : null}
      {view.note && <div className="body-small" style={{ marginTop: 6 }}>{view.note}</div>}
    </div>
  );
}

function extractedView(ext, extracted) {
  if (!extracted || extracted.status === "loading") {
    return { kind: "text", text: "",
             note: `extracting ${ext} text with the engine…` };
  }
  if (extracted.status === "err") {
    return { kind: "binary",
             note: `${ext} — no preview: ${extracted.errors.join("; ")}` };
  }
  let text = extracted.text;
  if (!text.trim()) {
    return { kind: "binary",
             note: `${ext} — no extractable text (scanned/image-only file?)` };
  }
  const clipped = text.length > PREVIEW_TEXT_CAP;
  if (clipped) text = text.slice(0, PREVIEW_TEXT_CAP);
  return { kind: "text", text,
           note: "text exactly as the engine scans it at run time"
             + (clipped
                ? ` · first ${PREVIEW_TEXT_CAP / 1000} K characters`
                : "") };
}

function buildPreview(file) {
  const ext = file.name.toLowerCase().split(".").pop();
  let text;
  try {
    text = decodeSourceBytes(b64ToBytes(file.b64));
  } catch {
    return { kind: "binary", note: "could not decode this file as text" };
  }
  const clipped = text.length > PREVIEW_TEXT_CAP;
  if (clipped) text = text.slice(0, PREVIEW_TEXT_CAP);

  if (ext === "csv") {
    const rows = parseCsv(text);
    if (!rows.length) return { kind: "text", text: "", note: "empty file" };
    const [head, ...body] = rows;
    const shown = body.slice(0, PREVIEW_ROW_CAP);
    const notes = [`${body.length} row${body.length === 1 ? "" : "s"} × ${head.length} columns`];
    if (body.length > shown.length) notes.push(`first ${shown.length} shown`);
    if (clipped) notes.push("preview truncated");
    return { kind: "table", head, body: shown, note: notes.join(" · ") };
  }
  if (ext === "json" && !clipped) {
    try {
      return { kind: "text",
               text: JSON.stringify(JSON.parse(text), null, 2), note: null };
    } catch (e) {
      return { kind: "text", text,
               note: `not valid JSON (${e.message}) — raw text shown` };
    }
  }
  return { kind: "text", text,
           note: clipped ? `first ${PREVIEW_TEXT_CAP / 1000} K characters shown` : null };
}

/** Decode ladder mirroring adapters/base.py: UTF-16 by BOM, else UTF-8
 *  (BOM-stripping), else cp1252. No content guessing beyond the BOM. */
function decodeSourceBytes(bytes) {
  if (bytes.length >= 2
      && ((bytes[0] === 0xff && bytes[1] === 0xfe)
          || (bytes[0] === 0xfe && bytes[1] === 0xff))) {
    const codec = bytes[0] === 0xff ? "utf-16le" : "utf-16be";
    return new TextDecoder(codec).decode(bytes.subarray(2));
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

/** Minimal quote-aware CSV split — for preview only; the engine has its own. */
function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.length > 1 || r[0] !== "");
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function bytesToB64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}
