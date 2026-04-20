#!/usr/bin/env python
"""Extract S/V/W/X chapter codes from icd10cm-order-2025.txt and write a TSV.

The order file format (fixed-width, CRLF):
  cols  0-4  : order number (5 chars)
  col   5    : space
  cols  6-12 : code (7 chars, left-justified, trailing spaces)
  col   13   : space
  col   14   : valid-billing flag ('1' = valid, '0' = header only)
  col   15   : space
  cols 16-75 : short description (60 chars)
  col   76   : space
  cols 77+   : long description

Only rows with flag='1' are imported (header/category rows are skipped).
"""

from __future__ import annotations

from pathlib import Path

MISSING_CHAPTERS = {"S", "V", "W", "X"}

ORDER_FILE = Path(__file__).parent.parent / "docs" / "medical-codes" / "icd10cm-order-2025.txt"
OUT_FILE   = Path(__file__).parent.parent / "docs" / "medical-codes" / "icd10cm_SVWX_2025.tsv"
CATALOG_VERSION = "ICD10CM-2025"


def main() -> None:
    rows: list[tuple[str, str]] = []

    with ORDER_FILE.open(encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\r\n")
            if len(line) < 77:
                continue

            flag  = line[14]
            if flag != "1":
                continue

            code  = line[6:13].strip()
            if not code or code[0].upper() not in MISSING_CHAPTERS:
                continue

            long_desc = line[77:].strip()
            if not long_desc:
                long_desc = line[16:76].strip()

            rows.append((code, long_desc))

    with OUT_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write("code\tdescription\tchapter\tcatalog_version\n")
        for code, desc in rows:
            chapter = code[0].upper()
            fh.write(f"{code}\t{desc}\t{chapter}\t{CATALOG_VERSION}\n")

    print(f"Written {len(rows):,} codes → {OUT_FILE}")
    chapter_counts: dict[str, int] = {}
    for code, _ in rows:
        ch = code[0].upper()
        chapter_counts[ch] = chapter_counts.get(ch, 0) + 1
    for ch in sorted(chapter_counts):
        print(f"  Chapter {ch}: {chapter_counts[ch]:,} codes")


if __name__ == "__main__":
    main()
