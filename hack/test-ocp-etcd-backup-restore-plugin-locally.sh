#!/usr/bin/env bash

# This script verifies that a ocp-etcd-backup-restore build can be installed to a system using
# krew local testing method

set -euo pipefail

[[ -n "${DEBUG:-}" ]] && set -x

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$SRC_ROOT"

build_dir="build"

ocp_etcd_backup_restore_manifest="${build_dir}/ocp-etcd-backup-restore.yaml"
if [[ ! -f "${ocp_etcd_backup_restore_manifest}" ]]; then
  echo >&2 "Could not find manifest ${ocp_etcd_backup_restore_manifest}."
  exit 1
fi

ocp_etcd_backup_restore_archive="${build_dir}/ocp-etcd-backup-restore.tar.gz"
if [[ ! -f "${ocp_etcd_backup_restore_archive}" ]]; then
  echo >&2 "Could not find archive ${ocp_etcd_backup_restore_archive}."
  exit 1
fi

# test for linux OS
kubectl krew install --manifest=$ocp_etcd_backup_restore_manifest --archive=$ocp_etcd_backup_restore_archive
kubectl krew uninstall ocp-etcd-backup-restore

# test for darwin OS
KREW_OS=darwin KREW_ARCH=amd64 kubectl krew install --manifest=$ocp_etcd_backup_restore_manifest --archive="$ocp_etcd_backup_restore_archive"
KREW_OS=darwin KREW_ARCH=amd64 kubectl krew uninstall ocp-etcd-backup-restore

echo >&2 "Successfully tested ocp-etcd-backup-restore plugin locally"
