"""Regenerate the binary T1 fixtures (cp1252 CSV + DOCX resumes).

Committed alongside the fixtures so they are reproducible artifacts, not
mystery blobs: `python tools/build_t1_binary_fixtures.py` rewrites them.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import docx

T1 = Path(__file__).resolve().parent.parent / "goldens" / "t1"


def cp1252_roster() -> None:
    # P20 The Encoding Victim: é stored as 0xE9 — utf-8 decoding fails, the
    # deterministic cp1252 fallback must recover the accents intact.
    rows = (
        "name,email,phone,current_company,title\n"
        "Renée Fontaine,renee.fontaine@example.com,+33 6 12 34 56 78,"
        "Café Lumière,Chef de Projet\n"
    )
    (T1 / "t1_cp1252.csv").write_bytes(rows.encode("cp1252"))


def _resume(name: str, lines: list[str]) -> None:
    doc = docx.Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(str(T1 / name))


def resumes() -> None:
    _resume("resume_p01.docx", [
        "Avery Stone",
        "avery.stone@example.com | +1 415 555 2671",
        "",
        "Staff Data Engineer at Marigold Data since Feb 2021",
        "Skills: Python, Airflow, SQL",
    ])
    # P03: the name line is deliberately NFD-decomposed — byte-different from
    # the roster's NFC "Núñez, Carlos", visually identical.
    _resume("resume_p03.docx", [
        unicodedata.normalize("NFD", "Carlos Núñez"),
        "carlos.nunez@example.com",
        "",
        "Platform Engineer at Vertex Cloud since 2022",
        "Skills: Kubernetes, Terraform",
    ])
    _resume("resume_p07.docx", [
        "Curriculum Vitae",  # name heuristic must decline this heading
        "Ishaan Verma — ishaan.verma@example.com",
        "",
        "Analyst at Quanta Insights 2019 - 2021",
        "Consultant at Meridian Partners 03/04/2021 - 11/2021",
    ])
    _resume("resume_p18.docx", [
        "Tomas Eder",
        "tomas.eder@example.com",
        "https://www.linkedin.com/in/tomas-eder?utm_campaign=profile",
        "https://github.com/teder",
        "Portfolio: https://tomas.dev",
        "",
        "Frontend Lead at Pixelforge since 2023",
    ])


if __name__ == "__main__":
    cp1252_roster()
    resumes()
    print("T1 binary fixtures rebuilt in", T1)
