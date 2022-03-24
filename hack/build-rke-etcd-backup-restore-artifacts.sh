#!/usr/bin/env bash

set -euo pipefail

set -x
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# create tvk-oneclick tar package
rke_etcd_backup_restore_tar_archive="rke-etcd-backup-restore.tar.gz"
echo >&2 "Creating ${rke_etcd_backup_restore_tar_archive} archive."

cd "$SRC_ROOT"
build_dir="build"
mkdir $build_dir
cp -r dist/rke-etcd-backup-restore $build_dir/
cp LICENSE.md $build_dir/rke-etcd-backup-restore/
cd $build_dir

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find . -print0)

tar -cvzf ${rke_etcd_backup_restore_tar_archive} rke-etcd-backup-restore/
echo >&2 "Created ${rke_etcd_backup_restore_tar_archive} archive successfully"

# create rke_etcd_backup_restore tar sha256 file
echo >&2 "Compute sha256 of ${rke_etcd_backup_restore_tar_archive} archive."

checksum_cmd="shasum -a 256"
if hash sha256sum 2>/dev/null; then
  checksum_cmd="sha256sum"
fi

rke_etcd_backup_restore_sha256_file=rke-etcd-backup-restore-sha256.txt
"${checksum_cmd[@]}" "${rke_etcd_backup_restore_tar_archive}" > $rke_etcd_backup_restore_sha256_file
ls -lrt
echo >&2 "Successfully written sha256 of ${rke_etcd_backup_restore_tar_archive} into $rke_etcd_backup_restore_sha256_file"
