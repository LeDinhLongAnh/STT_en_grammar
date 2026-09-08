#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# download_models.sh - fetch sherpa-onnx INT8 ASR models for the VCC project
#
# Runs on Linux/macOS and on Windows under Git Bash / MSYS2.
#
#   ./scripts/download_models.sh              # core set (small, router-ready)
#   ./scripts/download_models.sh --all        # core + extra (for A/B testing)
#   ./scripts/download_models.sh --list
#   ./scripts/download_models.sh --only sherpa-onnx-whisper-base.en
#   ./scripts/download_models.sh --keep-fp32  # keep the fp32 weights too
#   ./scripts/download_models.sh --force      # re-download / re-extract
#
# For each selected model the script
#   1. downloads the tarball into models/.cache (cached across runs),
#   2. extracts and flattens it into models/<id>/,
#   3. prunes the fp32 twin of every *.int8.onnx plus junk (*.pt, README, ...),
#   4. makes sure bpe.model + bpe.vocab exist so contextual biasing works,
#   5. rewrites models/MANIFEST.txt.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_BASE="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MODELS_DIR="$ROOT/models"
CACHE_DIR="$ROOT/models/.cache"
CATALOG="$HERE/models.catalog"
SOURCES="$HERE/bpe_sources.txt"
# Pick a python that can actually import sentencepiece. On Windows `python3` is
# often the Microsoft Store stub, which resolves but has no site-packages, so
# probing capability beats probing existence.
pick_python() {
  local c fallback=""
  for c in python3 python py; do
    command -v "$c" >/dev/null 2>&1 || continue
    [ -n "$fallback" ] || fallback="$(command -v "$c")"
    if "$c" -c "import sentencepiece" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  printf '%s' "$fallback"
}
PYBIN="$(pick_python)"

WANT_ALL=0
KEEP_FP32=0
ONLY=""
FORCE=0

die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  !!\033[0m %s\n' "$*"; }

usage() { sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --all)       WANT_ALL=1 ;;
    --keep-fp32) KEEP_FP32=1 ;;
    --force)     FORCE=1 ;;
    --only)      shift; ONLY="${1:-}"; [ -n "$ONLY" ] || die "--only needs a model id" ;;
    --list)      awk '!/^#/ && NF {printf "  %-58s %-11s %s\n", $1, $3, $4}' "$CATALOG"; exit 0 ;;
    -h|--help)   usage ;;
    *)           die "unknown option: $1 (try --help)" ;;
  esac
  shift
done

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v tar  >/dev/null 2>&1 || die "tar not found"
[ -f "$CATALOG" ] || die "catalog not found: $CATALOG"
mkdir -p "$MODELS_DIR" "$CACHE_DIR"

# --- helpers ---------------------------------------------------------------

fetch() {
  local url="$1"
  local dest="$2"
  if [ -s "$dest" ] && [ "$FORCE" -eq 0 ]; then
    ok "cached $(basename "$dest")"
    return 0
  fi
  info "downloading $(basename "$dest")"
  curl -fL --retry 3 --retry-delay 2 -# -o "$dest.part" "$url" \
    || die "download failed: $url"
  mv "$dest.part" "$dest"
}

sha1_of() {
  local f="$1"
  if   command -v sha1sum >/dev/null 2>&1; then sha1sum "$f" | cut -d' ' -f1
  elif command -v shasum  >/dev/null 2>&1; then shasum -a 1 "$f" | cut -d' ' -f1
  elif [ -n "$PYBIN" ]; then
    "$PYBIN" -c "import hashlib,sys;print(hashlib.sha1(open(sys.argv[1],'rb').read()).hexdigest())" "$f"
  else echo ""
  fi
}

# Keep the int8 weights, drop the fp32 twin when both are present.
prune_fp32() {
  local dir="$1"
  [ "$KEEP_FP32" -eq 1 ] && return 0
  local f base cand
  while IFS= read -r f; do
    base="${f%.int8.onnx}"
    for cand in "$base.onnx" "$base.fp32.onnx"; do
      if [ -f "$cand" ]; then
        rm -f "$cand"
        warn "pruned fp32 $(basename "$cand")"
      fi
    done
  done < <(find "$dir" -maxdepth 2 -name '*.int8.onnx' -print)
  return 0
}

# A bpe.model is only valid for the exact token inventory it was trained on, so
# scripts/bpe_sources.txt is keyed by the sha1 of tokens.txt rather than by name.
ensure_bpe_model() {
  local dir="$1"
  local toks="$dir/tokens.txt"
  [ -f "$dir/bpe.model" ] && return 0
  [ -f "$toks" ] || return 0
  [ -f "$SOURCES" ] || return 0
  local h url
  h="$(sha1_of "$toks")"
  [ -n "$h" ] || return 0
  url="$(awk -v h="$h" '!/^#/ && $1 == h { print $2; exit }' "$SOURCES")"
  if [ -z "$url" ]; then
    warn "no bpe.model source known for tokens.txt sha1=$h"
    warn "   -> word-level hotwords unavailable for this model"
    return 0
  fi
  info "fetching bpe.model matching tokens.txt sha1=$h"
  if curl -fL --retry 3 -sS -o "$dir/bpe.model" "$url"; then
    ok "bpe.model fetched"
  else
    warn "bpe.model download failed"
    rm -f "$dir/bpe.model"
  fi
  return 0
}

make_bpe_vocab() {
  local dir="$1"
  local spm="$dir/bpe.model"
  local out="$dir/bpe.vocab"
  [ -f "$spm" ] || return 0
  if [ -f "$out" ] && [ "$FORCE" -eq 0 ]; then ok "bpe.vocab present"; return 0; fi
  if [ -z "$PYBIN" ]; then
    warn "no python found: cannot derive bpe.vocab (hotwords disabled)"
    return 0
  fi
  if ! "$PYBIN" -c "import sentencepiece" >/dev/null 2>&1; then
    warn "python module 'sentencepiece' missing -> bpe.vocab not generated"
    warn "   fix: $PYBIN -m pip install sentencepiece   then rerun with --force"
    return 0
  fi
  if "$PYBIN" "$HERE/gen_bpe_vocab.py" "$spm" "$out" >/dev/null; then
    ok "generated bpe.vocab ($(wc -l < "$out" | tr -d ' ') pieces)"
  else
    warn "bpe.vocab generation failed"
  fi
  return 0
}

install_archive() {
  local id="$1"
  local asset="$2"
  local dest="$MODELS_DIR/$id"
  if [ -d "$dest" ] && [ "$FORCE" -eq 0 ]; then
    ok "already installed: $id"
    ensure_bpe_model "$dest"
    make_bpe_vocab "$dest"
    return 0
  fi
  fetch "$REPO_BASE/$asset" "$CACHE_DIR/$asset"
  info "extracting $asset"
  rm -rf "$dest" "$MODELS_DIR/.tmp-$id"
  mkdir -p "$MODELS_DIR/.tmp-$id"
  tar -xjf "$CACHE_DIR/$asset" -C "$MODELS_DIR/.tmp-$id"
  local top
  top="$(find "$MODELS_DIR/.tmp-$id" -mindepth 1 -maxdepth 1 -type d | head -1)"
  if [ -n "$top" ]; then mv "$top" "$dest"; else mv "$MODELS_DIR/.tmp-$id" "$dest"; fi
  rm -rf "$MODELS_DIR/.tmp-$id"
  find "$dest" -maxdepth 2 \( -name '*.pt' -o -name 'export*.sh' -o -name '*.md' \
       -o -name 'README*' -o -name '.gitattributes' \) -delete 2>/dev/null || true
  prune_fp32 "$dest"
  ensure_bpe_model "$dest"
  make_bpe_vocab "$dest"
  ok "installed $id ($(du -sh "$dest" 2>/dev/null | cut -f1))"
}

install_file() {
  local id="$1"
  local asset="$2"
  local dest="$MODELS_DIR/$id"
  mkdir -p "$dest"
  if [ -s "$dest/$asset" ] && [ "$FORCE" -eq 0 ]; then
    ok "already installed: $id/$asset"
    return 0
  fi
  fetch "$REPO_BASE/$asset" "$dest/$asset"
  ok "installed $id/$asset"
}

# --- main ------------------------------------------------------------------

selected=0
while read -r id asset family tier _rest; do
  case "$id" in ''|\#*) continue ;; esac
  if [ -n "$ONLY" ]; then
    [ "$id" = "$ONLY" ] || continue
  else
    [ "$tier" = "core" ] || [ "$WANT_ALL" -eq 1 ] || continue
  fi
  selected=$((selected+1))
  printf '\n\033[1m[%s]\033[0m family=%s tier=%s\n' "$id" "$family" "$tier"
  case "$asset" in
    *.tar.bz2) install_archive "$id" "$asset" ;;
    *)         install_file "$id" "$asset" ;;
  esac
done < <(grep -v '^[[:space:]]*#' "$CATALOG" | grep -v '^[[:space:]]*$')

[ "$selected" -gt 0 ] || die "nothing selected (bad --only id? try --list)"

MANIFEST="$MODELS_DIR/MANIFEST.txt"
{
  echo "# generated by scripts/download_models.sh"
  echo "# $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo
  find "$MODELS_DIR" -mindepth 2 -maxdepth 3 -type f \
       \( -name '*.onnx' -o -name 'tokens.txt' -o -name 'bpe.*' \) \
    | sed "s|^$MODELS_DIR/||" | sort
} > "$MANIFEST"

printf '\n'
info "models installed under $MODELS_DIR"
du -sh "$MODELS_DIR"/*/ 2>/dev/null | grep -v '\.cache' || true
printf '\n'
ok "manifest -> models/MANIFEST.txt"
ok "tarball cache in models/.cache (safe to delete)"
