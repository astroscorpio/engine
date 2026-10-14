# Astro Scorpio engine

This is the calculation service behind [astroscorpio.com](https://astroscorpio.com): the Vedic astrology engine and the JSON API that serves it. It is published under the GNU Affero General Public License v3 because it links the Swiss Ephemeris (AGPL edition). The rest of the site, the web front end and the API gateway, are separate programs that talk to this service over HTTP.

Every response from astroscorpio.com's API carries `engine.source`, a link to the exact tag of this repository that is deployed.

## Layout

| Path | What |
|---|---|
| `engine/` | `jyotisha`, the calculation engine: ephemeris, charts and the 16 vargas, dashas, ashtakavarga, strengths, yogas, panchanga, muhurta, tajika, transit events. Tests and `verify.py` included. |
| `engine/ephe/` | Swiss Ephemeris data files from Astrodienst (1800-2399), with checksums. |
| `compute/` | `astro_compute`, the JSON API over the engine (AWS Lambda handler and a local dev server), with its tests. Matching tables cite their sources line by line. |
| `build/` | Scripts that build the deployed Lambda package from this tree, including the pyswisseph extension. |
| `third_party/` | The exact pyswisseph source distribution compiled into the deployed service. |

## Run the tests

Python 3.12. pyswisseph builds from source, so a C compiler is needed.

```bash
python3.12 -m venv .venv
.venv/bin/pip install "pyswisseph==2.10.3.2" "pydantic>=2.9,<3" pytest
(cd engine && SE_EPHE_PATH=$PWD/ephe PYTHONPATH=. ../.venv/bin/python -m pytest -q && PYTHONPATH=. SE_EPHE_PATH=$PWD/ephe ../.venv/bin/python verify.py)
(cd compute && SE_EPHE_PATH=$PWD/../engine/ephe ../.venv/bin/python -m pytest -q)
```

Run the API locally: `cd compute && SE_EPHE_PATH=$PWD/../engine/ephe PYTHONPATH=.:../engine ../.venv/bin/python devserver.py 8790`, then `curl -s localhost:8790/v1/health`.

## Build the deployed package

```bash
build/build_lambda_zip.sh out/compute.zip
```

This compiles pyswisseph from `third_party/` with zig cc for glibc 2.17, so the extension loads on AWS Lambda's Amazon Linux. It also installs the pinned `build/requirements-lambda.txt` wheels and packs `compute/`, `engine/jyotisha` and `engine/ephe`. The handler is `lambda_function.handler` on Python 3.12, with `SE_EPHE_PATH=/var/task/ephe`.

## Method notes

- Sidereal zodiac, Lahiri ayanamsa by default (others selectable), true lunar node by default (mean selectable), whole-sign houses.
- Sunrise and sunset are the centre of the Sun's disc with refraction.
- Dasha years are 365.2425 days.
- The engine treats classical rules as textual conventions, not as validated predictions. See `engine/README.md`, "Known evidence limits".

## Licence

Copyright (c) 2026 Astro Scorpio. Licensed under the GNU Affero General Public License v3.0 or later. See `LICENSE`. Third-party components keep their own copyright and terms; see `NOTICE`.
