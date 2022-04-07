#!/usr/bin/env bash

# This script verifies that a tvk-quickstart build can be installed to a system using
# krew local testing method

set -euo pipefail

[[ -n "${DEBUG:-}" ]] && set -x

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$SRC_ROOT"

build_dir="build"

tvk_quickstart_manifest="${build_dir}/tvk-quickstart.yaml"
if [[ ! -f "${tvk_quickstart_manifest}" ]]; then
  echo >&2 "Could not find manifest ${tvk_quickstart_manifest}."
  exit 1
fi

tvk_quickstart_archive="${build_dir}/tvk-quickstart.tar.gz"
if [[ ! -f "${tvk_quickstart_archive}" ]]; then
  echo >&2 "Could not find archive ${tvk_quickstart_archive}."
  exit 1
fi

# test for linux OS
kubectl krew install --manifest=$tvk_quickstart_manifest --archive=$tvk_quickstart_archive
kubectl krew uninstall tvk-quickstart

# test for darwin OS
KREW_OS=darwin KREW_ARCH=amd64 kubectl krew install --manifest=$tvk_quickstart_manifest --archive="$tvk_quickstart_archive"
KREW_OS=darwin KREW_ARCH=amd64 kubectl krew uninstall tvk-quickstart

echo >&2 "Successfully tested Tvk-quickstart plugin locally"
