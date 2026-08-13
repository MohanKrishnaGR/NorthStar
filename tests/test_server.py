"""U5: workspace server — the same engine behind two endpoints."""
import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from transformer.server import TEMPLATE, Handler


@pytest.fixture(scope="module")
def base_url():
    if not TEMPLATE.exists():
        pytest.skip("built UI template missing (python tools/build_ui.py)")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def call(base, path, payload=None):
    url = base + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, json.dumps(payload).encode(),
            {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_ships_configs_samples_types(base_url):
    s, h = call(base_url, "/api/health")
    assert s == 200 and h["ok"]
    assert set(h["configs"]) == {"default", "recruiter_view"}
    assert "goldens/t1" in h["samples"]
    assert "skills[].name" in h["canonical_types"]


def test_sample_run_returns_bundle(base_url):
    _, h = call(base_url, "/api/health")
    s, b = call(base_url, "/api/run",
                {"sample": "samples", "config": h["configs"]["default"],
                 "as_of": "2026-08"})
    assert s == 200
    assert b["run"]["profiles"] == len([c for c in b["candidates"]
                                        if not c["excluded"]])
    assert any(c["canonical"]["full_name"] == "Alice Fern"
               for c in b["candidates"])


def test_uploaded_csv_runs_end_to_end(base_url):
    _, h = call(base_url, "/api/health")
    csv = ("name,email,phone,current_company,title\n"
           "Zed Upload,zed@example.com,+1 415 555 2671,Uploadify,QA\n")
    s, b = call(base_url, "/api/run", {
        "files": [{"name": "up.csv",
                   "b64": base64.b64encode(csv.encode()).decode()}],
        "config": h["configs"]["default"],
    })
    assert s == 200
    zed = b["candidates"][0]["canonical"]
    assert zed["full_name"] == "Zed Upload"
    assert zed["phones"] == ["+14155552671"]


def test_bad_config_is_400_with_named_errors(base_url):
    s, e = call(base_url, "/api/run", {
        "sample": "samples",
        "config": {"fields": [{"path": "x", "from": "emials[0]",
                               "type": "string"}]},
    })
    assert s == 400
    assert any("emials" in msg for msg in e["errors"])


def test_no_inputs_and_unknown_sample_rejected(base_url):
    _, h = call(base_url, "/api/health")
    s, e = call(base_url, "/api/run", {"config": h["configs"]["default"]})
    assert s == 400 and "no files" in e["errors"][0]
    s, e = call(base_url, "/api/run",
                {"sample": "../../etc", "config": h["configs"]["default"]})
    assert s == 400 and "unknown sample" in e["errors"][0]
