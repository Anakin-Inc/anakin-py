"""
Regenerate `src/anakin/countries.py` from the live API.

    curl -s https://api.anakin.io/v1/countries | python scripts/refresh_countries.py

Reads the JSON response on stdin (a list, or {"countries": [...]}, of
{"code", "name"} objects) and rewrites the SUPPORTED_COUNTRIES_RAW block.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "src" / "anakin" / "countries.py"


def main() -> int:
    data = json.load(sys.stdin)
    items = data.get("countries", data) if isinstance(data, dict) else data
    rows = sorted(
        ({"code": str(c["code"]).lower(), "name": c.get("name")} for c in items),
        key=lambda c: c["code"],
    )
    if len(rows) < 100:
        print(f"refusing to write: only {len(rows)} countries in input", file=sys.stderr)
        return 1
    block = "SUPPORTED_COUNTRIES_RAW: list[dict[str, str]] = [\n"
    block += "".join(f'    {{"code": {r["code"]!r}, "name": {r["name"]!r}}},\n' for r in rows)
    block += "]"
    source = TARGET.read_text()
    source = re.sub(
        r"SUPPORTED_COUNTRIES_RAW: list\[dict\[str, str\]\] = \[\n.*?\n\]",
        lambda _: block,
        source,
        count=1,
        flags=re.DOTALL,
    )
    source = re.sub(
        r"on \d{4}-\d{2}-\d{2} \(\d+ locations",
        f"on {datetime.date.today().isoformat()} ({len(rows)} locations",
        source,
        count=1,
    )
    TARGET.write_text(source)
    print(f"wrote {len(rows)} countries to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
