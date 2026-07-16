#!/usr/bin/env bash
# Download AVIRIS-3 L2A reflectance granules (ORNL DAAC, Earthdata-protected).
#
# AUTH: reads your NASA Earthdata Login from ~/.netrc — this script NEVER contains
# or echoes credentials. Set up ~/.netrc once (see scripts/README):
#   printf 'machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASS\n' >> ~/.netrc
#   chmod 600 ~/.netrc
#
# Usage:
#   scripts/download_aviris3.sh [urls_file]        # default: the Jan-23 Palisades list
#   head -8 <list> > /tmp/one_line.txt && scripts/download_aviris3.sh /tmp/one_line.txt   # test 1 flight line first
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/data/raw/aviris3"
URLS="${1:-$DEST/aviris3_jan23_palisades_urls.txt}"
mkdir -p "$DEST"

if [ ! -f "$HOME/.netrc" ] || ! grep -q "urs.earthdata.nasa.gov" "$HOME/.netrc"; then
  echo "ERROR: no Earthdata entry in ~/.netrc. Set it up first:"
  echo "  printf 'machine urs.earthdata.nasa.gov login YOUR_USER password YOUR_PASS\\n' >> ~/.netrc && chmod 600 ~/.netrc"
  exit 1
fi
[ -f "$URLS" ] || { echo "ERROR: url list not found: $URLS"; exit 1; }

COOKIES="$HOME/.urs_cookies"; : > "$COOKIES"
total=$(grep -cve '^[[:space:]]*$' "$URLS"); i=0; ok=0; fail=0
echo "Downloading $total granule(s) -> $DEST"
while IFS= read -r url; do
  [ -z "${url// }" ] && continue
  i=$((i+1)); fn="$DEST/$(basename "$url")"
  if [ -s "$fn" ]; then echo "[$i/$total] have it, skip $(basename "$url")"; ok=$((ok+1)); continue; fi
  echo "[$i/$total] $(basename "$url")"
  if wget --load-cookies "$COOKIES" --save-cookies "$COOKIES" --keep-session-cookies \
          --auth-no-challenge=on -c -nv -O "$fn" "$url"; then
    ok=$((ok+1))
  else
    echo "  FAILED (removing partial): $(basename "$url")"; rm -f "$fn"; fail=$((fail+1))
  fi
done < "$URLS"
echo "Done: $ok ok, $fail failed. Files in $DEST"
du -sh "$DEST" 2>/dev/null || true
