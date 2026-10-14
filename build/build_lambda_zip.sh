#!/usr/bin/env bash
# Build the AWS Lambda package of the compute service from this tree.
#   build/build_lambda_zip.sh out/compute.zip
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ZIP="$(realpath -m "${1:-$ROOT/out/compute.zip}")"
CACHE="${CACHE:-$HERE/cache}"
PKG="$CACHE/pkg"
rm -rf "$PKG" && mkdir -p "$PKG/ephe" "$(dirname "$ZIP")"
python3.12 -m pip install --quiet --target "$PKG" --platform manylinux2014_x86_64 \
  --implementation cp --python-version 3.12 --only-binary=:all: -r "$HERE/requirements-lambda.txt"
cp "$("$HERE/build_swisseph.sh")" "$PKG/"
cp -r "$ROOT/compute/astro_compute" "$ROOT/compute/lambda_function.py" "$PKG/"
cp -r "$ROOT/engine/jyotisha" "$PKG/"
(cd "$ROOT/engine/ephe" && sha256sum -c --quiet SHA256SUMS)
cp "$ROOT/engine/ephe/"{sepl_18.se1,semo_18.se1,sefstars.txt} "$PKG/ephe/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +
rm -f "$ZIP"
python3.12 - "$PKG" "$ZIP" <<'PY'
import os, sys, zipfile
pkg, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(pkg):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            z.write(path, os.path.relpath(path, pkg))
PY
echo "$ZIP"
