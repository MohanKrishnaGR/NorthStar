"""Regenerate the binary T2 hostile fixtures (encodings and fake binaries)."""
from __future__ import annotations

from pathlib import Path

T2 = Path(__file__).resolve().parent.parent / "goldens" / "t2"


def main() -> None:
    T2.mkdir(parents=True, exist_ok=True)
    # UTF-16 text: utf-8 decode fails; the cp1252 fallback yields NUL-riddled
    # junk that extracts nothing — documented honest miss, never a crash.
    (T2 / "utf16.txt").write_bytes(
        "Name: Ute Sechzehn\nemail: ute@example.com\n".encode("utf-16")
    )
    # Text bytes wearing a .pdf suffix: pdfplumber refuses; source skipped.
    (T2 / "fake.pdf").write_bytes(b"%PDF-not-really\njust text pretending\n")
    # Zero-byte JSON.
    (T2 / "empty.json").write_bytes(b"")
    # BOM'd but otherwise healthy CSV: must parse via utf-8-sig, one profile.
    (T2 / "bom.csv").write_bytes(
        "name,email,phone,current_company,title\n"
        "Bo Marker,bo.marker@example.com,,BOM Industries,Analyst\n".encode("utf-8-sig")
    )


if __name__ == "__main__":
    main()
    print("T2 binary fixtures rebuilt in", T2)
