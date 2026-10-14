# Gold Auto Trader loader.
# Source is stored as plain text chunks in the repo to avoid compressed-payload corruption.
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_parts = []
for _i in range(1, 8):
    _parts.append((_root / f"gold_auto_source_{_i}.txt").read_text(encoding="utf-8"))
_source = "".join(_parts)
exec(compile(_source, "2_Gold.py", "exec"), globals(), globals())
