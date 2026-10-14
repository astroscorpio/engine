"""The suite runs against the Swiss Ephemeris data files, as production does.

SE_EPHE_PATH wins when set; otherwise ../ephe is used when present
(scripts/fetch_ephe.sh, or the files shipped with the public source tree).
"""

from __future__ import annotations

import os
from pathlib import Path

_EPHE = Path(__file__).resolve().parents[1] / "ephe"
if not os.environ.get("SE_EPHE_PATH") and _EPHE.is_dir():
    os.environ["SE_EPHE_PATH"] = str(_EPHE)
