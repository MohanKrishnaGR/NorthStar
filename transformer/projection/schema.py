"""JSON Schema generated *from the config* (ADR-012): output is validated
against the requested shape, not a hardcoded one. The default schema is just
the identity config through this same code path."""
from __future__ import annotations

import jsonschema

from .config import Config

_LEAF = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "object": {"type": "object"},
    "string[]": {"type": "array", "items": {"type": "string"}},
    "number[]": {"type": "array", "items": {"type": "number"}},
    "object[]": {"type": "array", "items": {"type": "object"}},
}


def _nullable(leaf: dict) -> dict:
    out = dict(leaf)
    t = out["type"]
    out["type"] = [t, "null"] if isinstance(t, str) else t + ["null"]
    return out


def build(cfg: Config) -> dict:
    root: dict = {"type": "object", "properties": {}, "required": [],
                  "additionalProperties": False}
    for f in cfg.fields:
        node = root
        for name in f.out_parts[:-1]:
            props = node["properties"]
            child = props.setdefault(name, {
                "type": "object", "properties": {}, "required": [],
                "additionalProperties": False,
            })
            if name not in node["required"]:
                node["required"].append(name)
            node = child
        leaf = _LEAF[f.type]
        # A field can be absent only under on_missing=omit; under "null" it is
        # present-but-nullable, under "error" a missing value excludes the
        # whole record, so surviving records always carry the key.
        if f.required:
            node["properties"][f.out_parts[-1]] = leaf
            node["required"].append(f.out_parts[-1])
        elif cfg.on_missing == "omit":
            node["properties"][f.out_parts[-1]] = leaf
        else:
            node["properties"][f.out_parts[-1]] = _nullable(leaf)
            node["required"].append(f.out_parts[-1])
    if cfg.include_provenance:
        root["properties"]["provenance"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "source": {"type": "string"},
                    "method": {"type": "string"},
                    "alternatives": {"type": "array"},
                },
                "required": ["field", "source", "method"],
            },
        }
        root["required"].append("provenance")
    if cfg.include_confidence:
        root["properties"]["confidence"] = {
            "type": "object",
            "properties": {
                "overall": {"type": "number"},
                "fields": {"type": "object"},
            },
            "required": ["overall", "fields"],
        }
        root["required"].append("confidence")
    return root


def validate(record: dict, schema: dict) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(record)
    )
