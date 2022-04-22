#!/usr/bin/env bash
set -x
#SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" cd .. && pwd)"

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
# create rke-etcd-backup-restore tar package
rke_dir="rke_etcd_backup_restore"
rke_etcd_backup_restore_tar_linux="rke-etcd-backup-restore-Linux.tar.gz"
rke_etcd_backup_restore_tar_mac="rke-etcd-backup-restore-macOS.tar.gz"

cd "$SRC_ROOT" || exit
build_dir="build"
cd $build_dir || exit

# create rke_etcd_backup_restore tar sha256 file
echo >&2 "Compute sha256 of ${rke_etcd_backup_restore_tar_linux} archive."
echo >&2 "Compute sha256 of ${rke_etcd_backup_restore_tar_mac} archive."

checksum_cmd="shasum -a 256"
if hash sha256sum 2>/dev/null; then
  checksum_cmd="sha256sum"
fi

rke_etcd_backup_restore_sha256_file_linux="rke-etcd-backup-restore-Linux-sha256.txt"
rke_etcd_backup_restore_sha256_file_mac="rke-etcd-backup-restore-macOS-sha256.txt"
"${checksum_cmd[@]}" "${rke_etcd_backup_restore_tar_linux}" >$rke_etcd_backup_restore_sha256_file_linux
"${checksum_cmd[@]}" "${rke_etcd_backup_restore_tar_mac}" >$rke_etcd_backup_restore_sha256_file_mac

echo >&2 "Successfully written sha256 of ${rke_etcd_backup_restore_tar_linux} into $rke_etcd_backup_restore_sha256_file_linux"
echo >&2 "Successfully written sha256 of ${rke_etcd_backup_restore_tar_mac} into $rke_etcd_backup_restore_sha256_file_mac"
