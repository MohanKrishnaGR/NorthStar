// In-browser engine (UI_DESIGN §7, revisited for GitHub Pages): loads
// Pyodide + the project's own wheel and runs the REAL pipeline client-side.
// Same deterministic engine, zero servers — uploaded files never leave the
// browser, which for candidate PII is a stronger posture than any demo API.

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

const GLUE = `
import base64, json, tempfile, traceback
from pathlib import Path

from transformer.models import CANONICAL_TYPES
from transformer.normalize import dates
from transformer.pipeline import run_pipeline
from transformer.projection.config import ConfigError, load


def engine_info():
    from transformer import __version__
    from transformer.constants import SCORING_VERSION
    return json.dumps({
        "engine_version": __version__,
        "scoring_version": SCORING_VERSION,
        "canonical_types": CANONICAL_TYPES,
    })


def extract_json(payload_json):
    # Preview path: the resume adapter's own extractor, so what the user
    # sees is exactly what the pipeline will scan.
    try:
        p = json.loads(payload_json)
        from transformer.adapters.resume import extract_text
        target = (Path(tempfile.mkdtemp(prefix="extract_"))
                  / Path(str(p.get("name", ""))).name)
        target.write_bytes(base64.b64decode(p.get("b64", "")))
        return json.dumps({"ok": True, "text": extract_text(target)})
    except Exception as e:
        return json.dumps({"ok": False,
                           "errors": [f"{type(e).__name__}: {e}"]})


def run_json(payload_json):
    try:
        p = json.loads(payload_json)
        try:
            cfg = load(p.get("config") or {})
        except ConfigError as e:
            return json.dumps({"ok": False,
                               "errors": [f"config: {m}" for m in e.errors]})
        except ValueError as e:
            return json.dumps({"ok": False, "errors": [f"config: {e}"]})
        as_of = None
        if p.get("as_of"):
            as_of = dates.parse(str(p["as_of"]))
            if as_of is None:
                return json.dumps({"ok": False,
                                   "errors": [f"as_of {p['as_of']!r} is not a date"]})
        workdir = Path(tempfile.mkdtemp(prefix="run_"))
        inputs = []
        for f in p.get("files") or []:
            target = workdir / Path(str(f.get("name", ""))).name
            target.write_bytes(base64.b64decode(f.get("b64", "")))
            inputs.append(target)
        if not inputs:
            return json.dumps({"ok": False, "errors": ["no files staged"]})
        result = run_pipeline(inputs, cfg,
                              default_region=p.get("default_region") or None,
                              as_of=as_of, collect_ui=True)
        if result.readable_sources == 0:
            return json.dumps({"ok": False,
                               "errors": ["no readable sources in the uploaded set"]})
        return json.dumps({"ok": True, "bundle": result.ui_bundle})
    except Exception:
        return json.dumps({"ok": False, "errors": [traceback.format_exc(limit=3)]})
`;

let enginePromise = null;

/** The informative tail of a Python/JS error, for compact UI notes. */
function lastLine(e) {
  const lines = String(e).split("\n").map((s) => s.trim()).filter(Boolean);
  return (lines[lines.length - 1] ?? "unknown error").slice(0, 200);
}

export function loadBrowserEngine(onStatus) {
  if (!enginePromise) {
    enginePromise = boot(onStatus).catch((e) => {
      enginePromise = null; // allow retry after a failed load
      throw e;
    });
  }
  return enginePromise;
}

async function boot(onStatus) {
  onStatus("loading Pyodide runtime…");
  if (!window.loadPyodide) {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = PYODIDE_URL + "pyodide.js";
      s.onload = resolve;
      s.onerror = () => reject(new Error("could not load Pyodide from CDN"));
      document.head.appendChild(s);
    });
  }
  const pyodide = await window.loadPyodide({ indexURL: PYODIDE_URL });
  onStatus("installing engine packages (phonenumbers, jsonschema)…");
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(["phonenumbers", "jsonschema"]);
  onStatus("installing the transformer wheel…");
  // micropip requires PEP 427 wheel filenames, so a manifest carries the
  // real name instead of renaming the wheel. no-store: the manifest is the
  // deploy's version pointer — a stale cached copy means a stale engine.
  const manifest = await (await fetch(new URL("./engine_wheel.json",
                                              window.location),
                                      { cache: "no-store" })).json();
  await micropip.install(new URL(`./${manifest.wheel}`, window.location).href);
  // Resume extras, per format so one failure cannot take down the other;
  // the adapters degrade unsupported sources to skipped+reason either way.
  let docxSupport = false;
  let pdfSupport = false;
  const extrasFailed = {}; // ext -> last line of the real error
  onStatus("installing resume extras (docx/pdf — optional)…");
  try {
    // lxml and Pillow are Pyodide-built binaries; load them natively first
    // so micropip doesn't try (and fail) to build them from sdists.
    await pyodide.loadPackage(["lxml", "Pillow"]);
  } catch (e) {
    extrasFailed.docx = extrasFailed.pdf = lastLine(e);
  }
  if (!extrasFailed.docx) {
    try {
      await micropip.install("python-docx");
      docxSupport = true;
    } catch (e) { extrasFailed.docx = lastLine(e); }
  }
  if (!extrasFailed.pdf) {
    try {
      // Current pdfplumber requires Pillow>=12 (Pyodide 0.26 ships 10.2)
      // and pypdfium2 (no wasm build). Pin 0.11.4 with its exact pdfminer,
      // and deps=False to skip pypdfium2 — it only backs to_image, which
      // the pipeline never calls. Proven end-to-end in Node-Pyodide.
      await micropip.install("pdfminer.six==20231228");
      await micropip.install.callKwargs("pdfplumber==0.11.4", { deps: false });
      pdfSupport = true;
    } catch (e) { extrasFailed.pdf = lastLine(e); }
  }
  const missing = [!docxSupport && "docx", !pdfSupport && "pdf"]
    .filter(Boolean);
  const extrasNote = missing.length
    ? ` · ${missing.join("/")} extras unavailable (those sources will be `
      + "skipped with a reason)"
    : "";
  onStatus("starting engine…");
  pyodide.runPython(GLUE);
  const info = JSON.parse(pyodide.runPython("engine_info()"));
  const runner = pyodide.globals.get("run_json");
  const extractor = pyodide.globals.get("extract_json");
  const engine = {
    ...info,
    docxSupport,
    pdfSupport,
    extrasNote,
    resumeSupport: docxSupport && pdfSupport,
    run(payload) {
      const out = JSON.parse(runner(JSON.stringify(payload)));
      if (!out.ok) return Promise.reject(out.errors);
      return Promise.resolve(out.bundle);
    },
    extractText(payload) {
      const ext = String(payload.name ?? "").toLowerCase().split(".").pop();
      const supported = ext === "docx" ? docxSupport : pdfSupport;
      if (!supported) {
        return Promise.reject([
          `${ext} extras could not be installed in this browser — the run `
            + "will skip these sources with a reason",
          ...(extrasFailed[ext] ? [extrasFailed[ext]] : []),
        ]);
      }
      const out = JSON.parse(extractor(JSON.stringify(payload)));
      if (!out.ok) return Promise.reject(out.errors);
      return Promise.resolve(out.text);
    },
  };
  window.__browserEngine = engine; // console-testable hook
  onStatus("");
  return engine;
}
