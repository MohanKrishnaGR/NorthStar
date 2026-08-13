"""Adapter registry with deterministic detection (ADR-013).

Detection is by extension; candidates are offered to adapters in a fixed
order. Files no adapter claims are reported as unrecognized, never fatal.
"""
from __future__ import annotations

from pathlib import Path

from . import ats_json, github_json, linkedin_json, notes_txt, recruiter_csv

# Fixed order = deterministic. The recorded-response adapters claim their
# filename prefixes before the generic .json adapter sees the file.
_ADAPTERS = (recruiter_csv, github_json, linkedin_json, ats_json, notes_txt)


def detect_adapter(path: Path):
    for adapter in _ADAPTERS:
        if adapter.detect(path):
            return adapter
    try:  # resume support is an optional extra (pyproject [resume])
        from . import resume

        if resume.detect(path):
            return resume
    except ImportError:
        pass
    return None
