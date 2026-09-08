#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# fetch_sherpa_onnx.sh - install a prebuilt sherpa-onnx into third_party/
#
#   ./scripts/fetch_sherpa_onnx.sh                  # host default
#   ./scripts/fetch_sherpa_onnx.sh --platform linux-aarch64
#   ./scripts/fetch_sherpa_onnx.sh --version v1.13.6
#   ./scripts/fetch_sherpa_onnx.sh --list-platforms
#
# Layout produced (what CMakeLists.txt expects):
#   third_party/sherpa-onnx/include/sherpa-onnx/c-api/{c-api.h,cxx-api.h}
#   third_party/sherpa-onnx/lib/...
#
# Note: the official "-lib" archives ship only libraries, not headers, so the
# headers are pulled from the tagged source tree. They are fetched at the same
# version as the binaries, which is what keeps the ABI honest.
# ---------------------------------------------------------------------------
set -euo pipefail

VERSION="v1.13.6"
PLATFORM=""
FORCE=0

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DEST="$ROOT/third_party/sherpa-onnx"
CACHE="$ROOT/third_party/.cache"

die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  !!\033[0m %s\n' "$*"; }

# Archive name per platform, relative to the release tag.
# win-x64 uses the shared MD Release build: it matches the /MD runtime MSVC
# defaults to, and "no-tts" halves the download since this project is ASR only.
archive_for() {
  case "$1" in
    win-x64)        echo "sherpa-onnx-${VERSION}-win-x64-shared-MD-Release-no-tts-lib.tar.bz2" ;;
    win-x86)        echo "sherpa-onnx-${VERSION}-win-x86-shared-MD-Release-no-tts-lib.tar.bz2" ;;
    win-arm64)      echo "sherpa-onnx-${VERSION}-win-arm64-shared-MD-Release-no-tts-lib.tar.bz2" ;;
    linux-x64)      echo "sherpa-onnx-${VERSION}-linux-x64-shared.tar.bz2" ;;
    linux-aarch64)  echo "sherpa-onnx-${VERSION}-linux-aarch64-shared.tar.bz2" ;;
    linux-arm)      echo "sherpa-onnx-${VERSION}-linux-arm-shared.tar.bz2" ;;
    osx-arm64)      echo "sherpa-onnx-${VERSION}-osx-arm64-shared.tar.bz2" ;;
    osx-x64)        echo "sherpa-onnx-${VERSION}-osx-x86_64-shared.tar.bz2" ;;
    *)              echo "" ;;
  esac
}

detect_platform() {
  local os arch
  os="$(uname -s 2>/dev/null || echo unknown)"
  arch="$(uname -m 2>/dev/null || echo unknown)"
  case "$os" in
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
      case "$arch" in
        aarch64|arm64) echo "win-arm64" ;;
        i686|i386)     echo "win-x86" ;;
        *)             echo "win-x64" ;;
      esac ;;
    Linux)
      case "$arch" in
        aarch64|arm64) echo "linux-aarch64" ;;
        armv7l|armv6l) echo "linux-arm" ;;
        *)             echo "linux-x64" ;;
      esac ;;
    Darwin)
      case "$arch" in
        arm64) echo "osx-arm64" ;;
        *)     echo "osx-x64" ;;
      esac ;;
    *) echo "" ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)  shift; VERSION="${1:?--version needs a tag like v1.13.6}" ;;
    --platform) shift; PLATFORM="${1:?--platform needs a name}" ;;
    --force)    FORCE=1 ;;
    --list-platforms)
      for p in win-x64 win-x86 win-arm64 linux-x64 linux-aarch64 linux-arm osx-arm64 osx-x64; do
        printf '  %-16s %s\n' "$p" "$(archive_for "$p")"
      done
      exit 0 ;;
    -h|--help) sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v tar  >/dev/null 2>&1 || die "tar not found"

[ -n "$PLATFORM" ] || PLATFORM="$(detect_platform)"
[ -n "$PLATFORM" ] || die "cannot detect the platform; pass --platform (see --list-platforms)"

ASSET="$(archive_for "$PLATFORM")"
[ -n "$ASSET" ] || die "unknown platform '$PLATFORM' (see --list-platforms)"

if [ -f "$DEST/include/sherpa-onnx/c-api/c-api.h" ] && [ "$FORCE" -eq 0 ]; then
  ok "sherpa-onnx already installed in third_party/sherpa-onnx (use --force to replace)"
  exit 0
fi

mkdir -p "$CACHE"
URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/${VERSION}/${ASSET}"

info "platform : $PLATFORM"
info "version  : $VERSION"
info "asset    : $ASSET"

if [ ! -s "$CACHE/$ASSET" ]; then
  curl -fL --retry 3 --retry-delay 2 -# -o "$CACHE/$ASSET.part" "$URL" \
    || die "download failed: $URL"
  mv "$CACHE/$ASSET.part" "$CACHE/$ASSET"
else
  ok "using cached $ASSET"
fi

info "extracting"
rm -rf "$DEST" "$ROOT/third_party/.tmp-sherpa"
mkdir -p "$ROOT/third_party/.tmp-sherpa"
tar -xjf "$CACHE/$ASSET" -C "$ROOT/third_party/.tmp-sherpa"

TOP="$(find "$ROOT/third_party/.tmp-sherpa" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -n "$TOP" ] || die "unexpected archive layout"
mv "$TOP" "$DEST"
rm -rf "$ROOT/third_party/.tmp-sherpa"

[ -d "$DEST/lib" ] || die "no lib/ directory in the archive"

info "fetching matching headers"
mkdir -p "$DEST/include/sherpa-onnx/c-api"
for h in c-api.h cxx-api.h; do
  curl -fL --retry 3 -sS \
    -o "$DEST/include/sherpa-onnx/c-api/$h" \
    "https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/${VERSION}/sherpa-onnx/c-api/$h" \
    || die "cannot fetch $h for ${VERSION}"
done

printf '%s\n' "$VERSION" > "$DEST/VERSION"

ok "installed sherpa-onnx $VERSION ($PLATFORM) into third_party/sherpa-onnx"
printf '\n'
ls -1 "$DEST/lib" | sed 's/^/  lib\//'
printf '\n'
ok "next:  cmake -S . -B build && cmake --build build --config Release"
