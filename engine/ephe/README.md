# Swiss Ephemeris data files

Astrodienst's data files, unmodified, from https://github.com/aloistr/swisseph (`ephe/`), commit `aacf962d19d79f8bc921dbcdaacf306d85be1917`:

| File | Covers |
|---|---|
| `sepl_18.se1` | Planets, 1800-2399 (generated from JPL DE441) |
| `semo_18.se1` | Moon and lunar node, 1800-2399 |
| `sefstars.txt` | Fixed stars, used by the true-star ayanamsas (true Chitra, true Revati) |

Check them with `sha256sum -c SHA256SUMS`. They are part of the Swiss Ephemeris, Copyright (C) Astrodienst AG, and are used here under the AGPL option of Astrodienst's dual licence. Point the engine at this directory with `SE_EPHE_PATH`.
