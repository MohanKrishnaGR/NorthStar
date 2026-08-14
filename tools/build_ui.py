"""Build the explorer into ONE self-contained template.

Runs `npm run build`, then inlines the bundled JS and CSS into
ui/dist/explorer_template.html. The CLI's --emit-ui replaces the
"__RUN_DATA_JSON__" placeholder in that template with a run's data —
zero servers, zero installs for whoever opens the result.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui"
DIST = UI / "dist"


def main() -> int:
    # --inline-only: dist/ was already built (e.g. by the Dockerfile's node
    # stage); just do the inlining here where Python is available.
    if "--inline-only" not in sys.argv:
        got = subprocess.run(["npm", "run", "build"], cwd=UI,
                             shell=(sys.platform == "win32"),
                             capture_output=True, text=True)
        if got.returncode != 0:
            sys.stderr.write(got.stdout + got.stderr)
            return got.returncode

    html = (DIST / "index.html").read_text(encoding="utf-8")

    def inline_script(m: re.Match) -> str:
        src = m.group(1).lstrip("./")
        js = (DIST / src).read_text(encoding="utf-8")
        return f"<script type=\"module\">{js}</script>"

    def inline_css(m: re.Match) -> str:
        href = m.group(1).lstrip("./")
        css = (DIST / href).read_text(encoding="utf-8")
        return f"<style>{css}</style>"

    html = re.sub(
        r'<script type="module"[^>]*src="([^"]+)"[^>]*></script>',
        inline_script, html)
    html = re.sub(
        r'<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>', inline_css, html)

    out = DIST / "explorer_template.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    print(f"template -> {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
