#!/usr/bin/env bash

set -euo pipefail

set -x
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# create tvk-oneclick tar package
ocp_etcd_backup_restore_tar_archive="ocp-etcd-backup-restore.tar.gz"
echo >&2 "Creating ${ocp_etcd_backup_restore_tar_archive} archive."

cd "$SRC_ROOT"
build_dir="build"
mkdir $build_dir
cp -r dist/ocp-etcd-backup-restore $build_dir/
cp LICENSE.md $build_dir/ocp-etcd-backup-restore/
cd $build_dir

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find . -print0)

tar -cvzf ${ocp_etcd_backup_restore_tar_archive} ocp-etcd-backup-restore/
echo >&2 "Created ${ocp_etcd_backup_restore_tar_archive} archive successfully"

# create ocp_etcd_backup_restore tar sha256 file
echo >&2 "Compute sha256 of ${ocp_etcd_backup_restore_tar_archive} archive."

checksum_cmd="shasum -a 256"
if hash sha256sum 2>/dev/null; then
  checksum_cmd="sha256sum"
fi

ocp_etcd_backup_restore_sha256_file=ocp-etcd-backup-restore-sha256.txt
"${checksum_cmd[@]}" "${ocp_etcd_backup_restore_tar_archive}" >$ocp_etcd_backup_restore_sha256_file
echo >&2 "Successfully written sha256 of ${ocp_etcd_backup_restore_tar_archive} into $ocp_etcd_backup_restore_sha256_file"
