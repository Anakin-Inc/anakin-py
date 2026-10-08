"""
Generate `src/anakin/async_client.py` from `src/anakin/client.py`.

The sync client is the source of truth. Every public method there is a thin
wrapper `return self._run(ops.<op>(...))`, so the async flavour is a few
mechanical rewrites:

- `def method(` -> `async def method(` (public methods and `__call__`)
- `self._run(` -> `await self._run(`
- `SyncTransport` / `_SyncAPI` / `_SyncClientBase` -> async counterparts
- `XResource` -> `AsyncXResource`, `class Anakin` -> `class AsyncAnakin`

Usage:
    python scripts/generate_async.py          # write the file
    python scripts/generate_async.py --check  # exit 1 if it is out of date (CI)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "anakin" / "client.py"
DST = ROOT / "src" / "anakin" / "async_client.py"

HEADER = '''"""
Anakin async client.

    from anakin import AsyncAnakin

    async with AsyncAnakin(api_key="ak-...") as client:
        doc = await client.scrape("https://example.com")
        print(doc.markdown)

GENERATED FILE: do not edit. Source: `src/anakin/client.py`;
regenerate with `python scripts/generate_async.py`.
"""
'''


def transform(source: str) -> str:
    # Swap the module docstring for the async one.
    body = source.split('"""', 2)[2].lstrip("\n")
    out = HEADER + "\n" + body

    out = out.replace("SyncTransport", "AsyncTransport")
    out = out.replace("_SyncClientBase", "_AsyncClientBase")
    out = out.replace("_SyncAPI", "_AsyncAPI")
    out = re.sub(r"\b(\w+Resource)\b", r"Async\1", out)
    out = re.sub(r"\bclass Anakin\b", "class AsyncAnakin", out)
    out = out.replace('"""\n    Anakin SDK client.', '"""\n    Anakin SDK client (asyncio).')

    out = re.sub(r"^(\s+)def (?!_)(\w+)\(", r"\1async def \2(", out, flags=re.MULTILINE)
    out = re.sub(r"^(\s+)def __call__\(", r"\1async def __call__(", out, flags=re.MULTILINE)
    out = re.sub(r"(?<!await )self\._run\(", "await self._run(", out)
    # Docstring examples
    out = out.replace("matches = client.wire.discover(", "matches = await client.wire.discover(")
    out = out.replace("result = client.wire.run(", "result = await client.wire.run(")
    return out


def main() -> int:
    generated = transform(SRC.read_text())
    if "--check" in sys.argv:
        if not DST.exists() or DST.read_text() != generated:
            print(f"{DST.relative_to(ROOT)} is out of date; run python scripts/generate_async.py")
            return 1
        return 0
    DST.write_text(generated)
    print(f"wrote {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
