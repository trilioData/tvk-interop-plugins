#!/usr/bin/env bash
set -x
#SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" cd .. && pwd)"

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
# create ocp-etcd-backup-restore tar package
ocp_etcd_backup_restore_tar_linux="ocp-etcd-backup-restore-Linux.tar.gz"
ocp_etcd_backup_restore_tar_mac="ocp-etcd-backup-restore-macOS.tar.gz"

cd "$SRC_ROOT" || exit
build_dir="build"
cd $build_dir || exit
ocp_dir="ocp_etcd_backup_restore"

# create ocp_etcd_backup_restore tar sha256 file
echo >&2 "Compute sha256 of ${ocp_etcd_backup_restore_tar_linux} archive."
echo >&2 "Compute sha256 of ${ocp_etcd_backup_restore_tar_mac} archive."

checksum_cmd="shasum -a 256"
if hash sha256sum 2>/dev/null; then
  checksum_cmd="sha256sum"
fi

ocp_etcd_backup_restore_sha256_file_linux="ocp-etcd-backup-restore-Linux-sha256.txt"
ocp_etcd_backup_restore_sha256_file_mac="ocp-etcd-backup-restore-macOS-sha256.txt"
"${checksum_cmd[@]}" $ocp_dir/"${ocp_etcd_backup_restore_tar_linux}" >$ocp_dir/$ocp_etcd_backup_restore_sha256_file_linux
"${checksum_cmd[@]}" $ocp_dir/"${ocp_etcd_backup_restore_tar_mac}" >$ocp_dir/$ocp_etcd_backup_restore_sha256_file_mac

echo >&2 "Successfully written sha256 of ${ocp_etcd_backup_restore_tar_linux} into $ocp_dir/$ocp_etcd_backup_restore_sha256_file_linux"
echo >&2 "Successfully written sha256 of ${ocp_etcd_backup_restore_tar_mac} into $ocp_dir/$ocp_etcd_backup_restore_sha256_file_mac"
