#!/usr/bin/env bash

set -e -o pipefail

echo >&2 "Creating ocp-etcd-backup-restore plugin manifest yaml"
set -x

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$SRC_ROOT"

# get current git tag
# shellcheck disable=SC1090
source "$SRC_ROOT"/hack/get-git-tag.sh

build_dir="build"

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find $build_dir -print0)

ocp_etcd_backup_restore_yaml="ocp-etcd-backup-restore.yaml"
ocp_etcd_backup_restore_dir="ocp_etcd_backup_plugin"
cp .krew/$ocp_etcd_backup_restore_yaml $build_dir/$ocp_etcd_backup_restore_yaml

ocp_etcd_backup_restore_yaml=$build_dir/$ocp_etcd_backup_restore_yaml

tar_checksum="$(awk '{print $1}' $build_dir/ocp-etcd-backup-restore-sha256.txt)"
sed -i "s/OCP_ETCD_BACKUP_RESTORE_TAR_CHECKSUM/${tar_checksum}/g" $ocp_etcd_backup_restore_yaml
# shellcheck disable=SC2154
sed -i "s/OCP_ETCD_BACKUP_RESTORE_VERSION/$git_version/g" $ocp_etcd_backup_restore_yaml

echo >&2 "Written out $ocp_etcd_backup_restore_yaml"
