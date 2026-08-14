"""Local workspace server: the real engine behind two endpoints, stdlib only.

    python -m transformer serve [--port 8765]

GET  /             the explorer shell (no run data; workspace opens first)
GET  /api/health   shipped configs, sample corpora, canonical type map
GET  /api/sample?name=<corpus>   the corpus files as {name,size,b64} — the
                    UI stages them; running stays a separate, explicit act
POST /api/run      {files:[{name,b64}] | sample:<name>, config:{...},
                    as_of?, default_region?}  ->  UI bundle (or 400 + errors)
POST /api/extract  {name, b64} (docx/pdf) -> {text} via the resume
                    adapter's own extractor, so previews match the run

Binds 127.0.0.1 only — a demo/dev surface, not a deployment. Uploads land in
a fresh temp directory per run; nothing persists. The engine invoked here is
byte-for-byte the CLI's: same pipeline, same validation, same bundle.
"""
from __future__ import annotations

import base64
import json
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .adapters import resume
from .models import CANONICAL_TYPES
from .normalize import dates
from .pipeline import run_pipeline
from .projection.config import ConfigError, load

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "ui" / "dist" / "explorer_template.html"
SAMPLES = {"samples": ROOT / "samples", "goldens/t1": ROOT / "goldens" / "t1"}
_MAX_FILE = 5 * 1024 * 1024
_MAX_FILES = 60
_NAME_RE = re.compile(r"^[\w][\w .\-]{0,120}$")


def _shipped_configs() -> dict:
    out = {}
    for name in ("default", "recruiter_view"):
        p = ROOT / "configs" / f"{name}.json"
        out[name] = json.loads(p.read_text(encoding="utf-8"))
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet; the terminal is the demo
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html", "/explorer.html"):
            html = TEMPLATE.read_text(encoding="utf-8").replace(
                "\"__RUN_DATA_JSON__\"", "null")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/health":
            self._json(200, {
                "ok": True,
                "configs": _shipped_configs(),
                "samples": sorted(SAMPLES),
                "canonical_types": CANONICAL_TYPES,
            })
        elif path == "/api/sample":
            name = (parse_qs(query).get("name") or [""])[0]
            base = SAMPLES.get(name)
            if base is None:
                self._json(404, {"errors": [f"unknown sample corpus {name!r}"]})
                return
            self._json(200, {"files": [
                {"name": p.name, "size": p.stat().st_size,
                 "b64": base64.b64encode(p.read_bytes()).decode("ascii")}
                for p in sorted(base.iterdir()) if p.is_file()
            ]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/api/run", "/api/extract"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"errors": ["request body is not valid JSON"]})
            return
        try:
            handler = _extract if self.path == "/api/extract" else _run
            self._json(200, handler(payload))
        except _BadRequest as e:
            self._json(400, {"errors": e.errors})
        except Exception as e:  # engine bugs surface honestly, not as hangs
            self._json(500, {"errors": [f"{type(e).__name__}: {e}"]})


class _BadRequest(Exception):
    def __init__(self, errors):
        self.errors = errors


def _decode_upload(payload: dict) -> tuple[str, bytes]:
    name = Path(str(payload.get("name", ""))).name
    if not _NAME_RE.match(name):
        raise _BadRequest([f"unacceptable file name {payload.get('name')!r}"])
    try:
        blob = base64.b64decode(payload.get("b64", ""), validate=True)
    except Exception:
        raise _BadRequest([f"{name}: broken base64 payload"])
    if len(blob) > _MAX_FILE:
        raise _BadRequest([f"{name}: over the {_MAX_FILE // 2**20}MB cap"])
    return name, blob


def _extract(payload: dict) -> dict:
    """Text of one staged docx/pdf, via the resume adapter's own extractor."""
    name, blob = _decode_upload(payload)
    if Path(name).suffix.lower() not in {".docx", ".pdf"}:
        raise _BadRequest([f"{name}: only docx/pdf need engine extraction"])
    target = Path(tempfile.mkdtemp(prefix="transformer_extract_")) / name
    target.write_bytes(blob)
    try:
        text = resume.extract_text(target)
    except ImportError:
        raise _BadRequest(
            ["resume extras not installed — pip install .[resume]"])
    except Exception as e:
        raise _BadRequest([f"{name}: {type(e).__name__}: {e}"])
    return {"text": text}


def _run(payload: dict) -> dict:
    try:
        cfg = load(payload.get("config") or {})
    except ConfigError as e:
        raise _BadRequest([f"config: {m}" for m in e.errors])
    except ValueError as e:
        raise _BadRequest([f"config: {e}"])

    as_of = None
    if payload.get("as_of"):
        as_of = dates.parse(str(payload["as_of"]))
        if as_of is None:
            raise _BadRequest([f"as_of {payload['as_of']!r} is not a date"])

    sample = payload.get("sample")
    if sample is not None:
        base = SAMPLES.get(sample)
        if base is None:
            raise _BadRequest([f"unknown sample corpus {sample!r}"])
        inputs = [p for p in base.iterdir() if p.is_file()]
    else:
        files = payload.get("files") or []
        if not files:
            raise _BadRequest(["no files uploaded and no sample selected"])
        if len(files) > _MAX_FILES:
            raise _BadRequest([f"too many files (max {_MAX_FILES})"])
        workdir = Path(tempfile.mkdtemp(prefix="transformer_run_"))
        inputs = []
        for f in files:
            name, blob = _decode_upload(f)
            target = workdir / name
            target.write_bytes(blob)
            inputs.append(target)

    result = run_pipeline(
        inputs, cfg,
        default_region=payload.get("default_region") or None,
        as_of=as_of, collect_ui=True,
    )
    if result.readable_sources == 0:
        raise _BadRequest(["no readable sources in the uploaded set"])
    return result.ui_bundle


def serve(port: int = 8765, host: str = "127.0.0.1") -> int:
    if not TEMPLATE.exists():
        print("serve needs the built template at ui/dist/explorer_template.html "
              "(run: python tools/build_ui.py)")
        return 2
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"workspace -> http://{shown}:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
