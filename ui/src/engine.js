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
  // real name instead of renaming the wheel.
  const manifest = await (await fetch(new URL("./engine_wheel.json",
                                              window.location))).json();
  await micropip.install(new URL(`./${manifest.wheel}`, window.location).href);
  let resumeSupport = true;
  try {
    onStatus("installing resume extras (docx/pdf — optional)…");
    // lxml and Pillow are Pyodide-built binaries; load them natively first
    // so micropip doesn't try (and fail) to build them from sdists.
    await pyodide.loadPackage(["lxml", "Pillow"]);
    await micropip.install(["python-docx", "pdfplumber"]);
  } catch {
    resumeSupport = false; // adapters degrade those sources to skipped+reason
  }
  onStatus("starting engine…");
  pyodide.runPython(GLUE);
  const info = JSON.parse(pyodide.runPython("engine_info()"));
  const runner = pyodide.globals.get("run_json");
  const engine = {
    ...info,
    resumeSupport,
    run(payload) {
      const out = JSON.parse(runner(JSON.stringify(payload)));
      if (!out.ok) return Promise.reject(out.errors);
      return Promise.resolve(out.bundle);
    },
  };
  window.__browserEngine = engine; // console-testable hook
  onStatus("");
  return engine;
}
