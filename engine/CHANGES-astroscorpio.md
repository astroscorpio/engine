# Changes made for astroscorpio.com

The engine is the jyotisha package as of 14 Oct 2026, with the changes below. Each one keeps the engine's existing results and its tests passing.

| File | Change | Why |
|---|---|---|
| `ephemeris.py` | `moon_rise_set(start, end, lat, lon)`, new | Panchang moonrise and moonset. Disc centre with refraction, the same convention as `sunrise`. |
| `ephemeris.py` | `luminaries(jd, ayanamsa)`, new | Sun and Moon only, computed exactly as `positions()` computes them. |
| `ephemeris.py` | `crossings(body, start, end, width, ...)`, new | Sign (width 30) and nakshatra (width 360/27) ingresses, with the boundary longitude and the speed there. `ingress_dates` is unchanged. |
| `muhurta.py` | `tithi_at`, `nakshatra_at`, `yoga_at`, `karana_at`, `_elongation` and the Moon-sign scan in `day()` use `luminaries()` | Identical values, about 5x faster panchang (404 ms to 70 ms per day). Verified byte-identical against the pre-change output. |
| `muhurta.py` | `evaluate`, `check` and `find` accept `natal_moon=None` / `natal_lagna=None` | Muhurta without a birth chart. Rules relative to the birth chart (tara, chandrashtama, lagna 8th from birth, Moon 4th/12th from the birth Moon) are skipped rather than guessed. |
| `ashtakavarga.py` | `_bhinna_cached` stores a weakref and checks identity; the cache is bounded | A bug in long-running processes. The cache was keyed on `id(chart)`, and CPython reuses a freed object's id, so a new chart could be served a dead chart's bindus. |
| `yogas.py` | Sankhya yoga reason reads "1 sign" / "5 signs" instead of "5 sign(s)" | Display text. |
