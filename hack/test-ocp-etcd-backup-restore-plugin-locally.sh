#!/usr/bin/env bash

# This script verifies that a ocp-etcd-backup-restore build can be installed to a system using

# krew local testing method

set -euo pipefail

set -x
[[ -n "${DEBUG:-}" ]] && set -x

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$SRC_ROOT"

ocp_dir="ocp_etcd_backup_restore"
build_dir="build/$ocp_dir"

ocp_etcd_backup_restore_manifest="${build_dir}/ocp-etcd-backup-restore.yaml"
if [[ ! -f "${ocp_etcd_backup_restore_manifest}" ]]; then
  echo >&2 "Could not find manifest ${ocp_etcd_backup_restore_manifest}."
  exit 1
fi

ocp_etcd_backup_restore_tar="ocp-etcd-backup-restore-Linux.tar.gz"
ocp_etcd_backup_restore_archive="${build_dir}/${ocp_etcd_backup_restore_tar}"
if [[ ! -f "${ocp_etcd_backup_restore_archive}" ]]; then
  echo >&2 "Could not find archive ${ocp_etcd_backup_restore_archive}."
  exit 1
fi

export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"

# test for linux OS
sudo kubectl krew install --manifest=$ocp_etcd_backup_restore_manifest --archive=$ocp_etcd_backup_restore_archive
sudo kubectl krew uninstall ocp-etcd-backup-restore

ocp_etcd_backup_restore_tar="ocp-etcd-backup-restore-macOS.tar.gz"
ocp_etcd_backup_restore_archive="${build_dir}/${ocp_etcd_backup_restore_tar}"
if [[ ! -f "${ocp_etcd_backup_restore_archive}" ]]; then
  echo >&2 "Could not find archive ${ocp_etcd_backup_restore_archive}."
  exit 1
fi

# test for darwin OS
KREW_OS=darwin KREW_ARCH=amd64 sudo kubectl krew install --manifest=$ocp_etcd_backup_restore_manifest --archive="$ocp_etcd_backup_restore_archive"
KREW_OS=darwin KREW_ARCH=amd64 sudo kubectl krew uninstall ocp-etcd-backup-restore

echo >&2 "Successfully tested ocp-etcd-backup-restore plugin locally"
