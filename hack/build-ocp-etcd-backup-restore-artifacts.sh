#!/usr/bin/env bash

set -euo pipefail

set -x
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# create ocp-etcd-backup-restore tar package
# shellcheck disable=SC2154
ocp_etcd_backup_restore_tar_archive="ocp-etcd-backup-restore-${platform}.tar.gz"
echo >&2 "Creating ${ocp_etcd_backup_restore_tar_archive} archive."

cd "$SRC_ROOT" || exit
build_dir="build"
mkdir $build_dir
cp -r dist/ocp-etcd-backup-restore $build_dir/
cp LICENSE.md $build_dir/
cd $build_dir

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find . -print0)

touch "${ocp_etcd_backup_restore_tar_archive}"
tar --exclude="${ocp_etcd_backup_restore_tar_archive}" -cvzf "${ocp_etcd_backup_restore_tar_archive}" .
echo >&2 "Created ${ocp_etcd_backup_restore_tar_archive} archive successfully"
cd "$SRC_ROOT"
