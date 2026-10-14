#!/usr/bin/env bash
# Compile the pyswisseph extension from third_party/ for CPython 3.12 on x86_64
# Linux, linked against glibc 2.17 so it also loads on AWS Lambda (Amazon Linux
# 2023, glibc 2.34). A native build on a newer distribution pulls in GLIBC_2.38
# symbols that Lambda lacks. Built without the optional swephelp/sqlite helpers.
#   build/build_swisseph.sh            -> prints the path of the built .so
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CACHE="${CACHE:-$HERE/cache}"
VERSION=2.10.3.2
SDIST="$ROOT/third_party/pyswisseph-$VERSION.tar.gz"
SDIST_SHA256=c54c305e83dbd5d2b71e58d8a69d8ee41de24c4d3328ce09e2af860a3537624d
OUT="$CACHE/so/swisseph.cpython-312-x86_64-linux-gnu.so"
[[ -s "$OUT" ]] && { echo "$OUT"; exit 0; }
echo "$SDIST_SHA256  $SDIST" | sha256sum -c --quiet
mkdir -p "$CACHE/so" "$CACHE/pyinc/x86_64-linux-gnu/python3.12"
[[ -x "$CACHE/zvenv/bin/python" ]] || {
  python3.12 -m venv "$CACHE/zvenv" && "$CACHE/zvenv/bin/pip" install -q "ziglang==0.17.0"
}
rm -rf "$CACHE/src" && mkdir -p "$CACHE/src" && tar xzf "$SDIST" -C "$CACHE/src"
# Debian's pyconfig.h includes a multiarch copy; expose only that file, never /usr/include,
# so zig's glibc 2.17 headers are the ones used.
INC="$(python3.12 -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
MULTI="/usr/include/x86_64-linux-gnu/python3.12/pyconfig.h"
[[ -f "$MULTI" ]] && cp "$MULTI" "$CACHE/pyinc/x86_64-linux-gnu/python3.12/"
cd "$CACHE/src/pyswisseph-$VERSION"
"$CACHE/zvenv/bin/python" -m ziglang cc -target x86_64-linux-gnu.2.17 -O2 -fPIC -shared \
  -fno-sanitize=all -DPYSWE_USE_SWEPHELP=0 -Ilibswe -I"$INC" -I"$CACHE/pyinc" \
  pyswisseph.c libswe/swecl.c libswe/swedate.c libswe/swehel.c libswe/swehouse.c \
  libswe/swejpl.c libswe/swemmoon.c libswe/swemplan.c libswe/sweph.c libswe/swephlib.c \
  -lm -o "$OUT" 2>/dev/null
if objdump -T "$OUT" | grep -qE "GLIBC_2\.(1[89]|[2-9][0-9])"; then
  echo "unexpected glibc symbol versions in $OUT" >&2; exit 1
fi
echo "$OUT"
