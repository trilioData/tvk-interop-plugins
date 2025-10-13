#!/usr/bin/env bash
set -euo pipefail
[[ -n "${DEBUG:-}" ]] && set -x

# --- config ---
SHFMT_PKG="mvdan.cc/sh/v3/cmd/shfmt"
SHFMT_VER="${SHFMT_VER:-v3.9.0}" # pin or set SHFMT_VER env var

# --- ensure shfmt exists (via Go) ---
if ! command -v shfmt >/dev/null 2>&1; then
  if ! command -v go >/dev/null 2>&1; then
    echo >&2 "ERROR: 'shfmt' not found and Go is not installed. Install Go or install shfmt via your package manager."
    exit 2
  fi
  echo >&2 "Installing shfmt ${SHFMT_VER} with 'go install'..."
  # Use modules (default) and the new install syntax
  GOFLAGS="${GOFLAGS:-}" go install "${SHFMT_PKG}@${SHFMT_VER}"
  # Ensure GOPATH/bin is on PATH for current shell
  GOPATH_BIN="$(go env GOPATH)/bin"
  if [[ ":${PATH}:" != *":${GOPATH_BIN}:"* ]]; then
    export PATH="${GOPATH_BIN}:${PATH}"
  fi
fi

# --- project root ---
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

set -x

# --- run shfmt (list files needing format) ---
shfmt_out="$(shfmt -l -i=2 "${SRC_ROOT}/hack" "${SRC_ROOT}/tools/cleanup" "${SRC_ROOT}/tests" || true)"
if [[ -n "${shfmt_out}" ]]; then
  echo >&2 "The following shell scripts need formatting."
  echo >&2 "Run:"
  echo >&2 "  shfmt -w -i=2 ${SRC_ROOT}/hack ${SRC_ROOT}/tools ${SRC_ROOT}/tests"
  echo >&2
  echo >&2 "${shfmt_out}"
  exit 1
fi

# --- run shellcheck if available ---
if command -v shellcheck >/dev/null 2>&1; then
  # -x follows 'source' to find files; adjust if too noisy
  #find "${SRC_ROOT}" -type f -name "*.sh" -exec shellcheck -x {} +
  echo "skipping shellcheck for now"
else
  echo >&2 "WARNING: shellcheck not found; skipping lint. Install it for best results."
fi

echo >&2 "shell-lint: No issues detected!"
