#!/usr/bin/env bash

set -e -o pipefail

set -x
echo >&2 "Creating rke-etcd-backup-restore plugin manifest yaml"

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$SRC_ROOT"

# get current git tag
# shellcheck disable=SC1090
source "$SRC_ROOT"/hack/get-git-tag.sh

rke_dir="rke_etcd_backup_restore"
build_dir="build/$rke_dir"

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find $build_dir -print0)

rke_etcd_backup_restore_yaml="rke-etcd-backup-restore.yaml"
cp .krew/$rke_etcd_backup_restore_yaml $build_dir/$rke_etcd_backup_restore_yaml

rke_etcd_backup_restore_yaml=$build_dir/$rke_etcd_backup_restore_yaml

# shellcheck disable=SC2154
#rke_etcd_backup_restore_tar="rke-etcd-backup-restore-Linux.tar.gz"
tar_checksum="$(awk '{print $1}' $build_dir/rke-etcd-backup-restore-Linux-sha256.txt)"
sed -i "s/RKE_ETCD_BACKUP_RESTORE_LINUX_TAR_CHECKSUM/${tar_checksum}/g" $rke_etcd_backup_restore_yaml

# shellcheck disable=SC2154
#rke_etcd_backup_restore_tar="rke-etcd-backup-restore-macOS.tar.gz"
tar_checksum="$(awk '{print $1}' $build_dir/rke-etcd-backup-restore-macOS-sha256.txt)"
sed -i "s/RKE_ETCD_BACKUP_RESTORE_MAC_TAR_CHECKSUM/${tar_checksum}/g" $rke_etcd_backup_restore_yaml

# shellcheck disable=SC2154
sed -i "s/RKE_ETCD_BACKUP_RESTORE_VERSION/$git_version/g" $rke_etcd_backup_restore_yaml

echo >&2 "Written out $rke_etcd_backup_restore_yaml"
