# Gold Auto Trader — generated from the validated source bundle.
# Keep Kalshi private keys in Streamlit Secrets, never in this repository.
import base64 as _b64, zlib as _z
from pathlib import Path as _Path
_root = _Path(__file__).resolve().parent.parent
_payload = "".join((_root / f"gold_auto_payload_{i}.txt").read_text().strip() for i in range(1, 4))
exec(compile(_z.decompress(_b64.b64decode(_payload)).decode("utf-8"), "2_Gold.py", "exec"), globals(), globals())
