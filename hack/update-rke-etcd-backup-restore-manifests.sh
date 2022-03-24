#!/bin/bash

set -e -o pipefail

if [[ -z "${RKE_ETCD_BACKUP_RESTORE_VERSION}" ]]; then
  echo >&2 "RKE_ETCD_BACKUP_RESTORE_VERSION (required) is not set"
  exit 1
else
  echo "RKE_ETCD_BACKUP_RESTORE_VERSION is set to ${RKE_ETCD_BACKUP_RESTORE_VERSION}"
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
# shellcheck disable=SC2164
cd "$SRC_ROOT"

plugins_dir="$SRC_ROOT"/plugins
build_dir="$SRC_ROOT"/build
template_manifest_dir="$SRC_ROOT"/.krew
rke_etcd_backup_restore_yaml="rke-etcd-backup-restore.yaml"
rke_etcd_backup_restore_template_manifest=$template_manifest_dir/$rke_etcd_backup_restore_yaml

mkdir -p "${build_dir}"

# shellcheck disable=SC2086
cp "$rke_etcd_backup_restore_template_manifest" $build_dir/$rke_etcd_backup_restore_yaml
rke_etcd_backup_restore_template_manifest=$build_dir/$rke_etcd_backup_restore_yaml

repoURL=$(git config --get remote.origin.url)
rkeetcdbackuprestoreSha256File="rke-etcd-backup-restore-sha256.txt"

rkeetcdbackuprestoreSha256URI="$repoURL/releases/download/${RKE_ETCD_BACKUP_RESTORE_VERSION}/$rkeetcdbackuprestoreSha256File"
rkeetcdbackuprestoreSha256FilePath=$build_dir/$rkeetcdbackuprestoreSha256File

curl -fsSL "$rkeetcdbackuprestoreSha256URI" >"${rkeetcdbackuprestoreSha256FilePath}"

if [ -s "${rkeetcdbackuprestoreSha256FilePath}" ]; then
  echo "File ${rkeetcdbackuprestoreSha256FilePath} successfully downloaded and contains data"
else
  echo "File ${rkeetcdbackuprestoreSha256FilePath} does not contain any data. Exiting..."
  exit 1
fi

rke_etcd_backup_restore_sha=$(awk '{print $1}' "$rkeetcdbackuprestoreSha256FilePath")

sed -i "s/RKE_ETCD_BACKUP_RESTORE_VERSION/$RKE_ETCD_BACKUP_RESTORE_VERSION/g" "$rke_etcd_backup_restore_template_manifest"
sed -i "s/RKE_ETCD_BACKUP_RESTORE_TAR_CHECKSUM/$rke_etcd_backup_restore_sha/g" "$rke_etcd_backup_restore_template_manifest"

cp "$build_dir"/$rke_etcd_backup_restore_yaml "$plugins_dir"/$rke_etcd_backup_restore_yaml
echo >&2 "Updated rke-etcd-backup-restore plugin manifest '$rke_etcd_backup_restore_template_manifest' with 'version=$RKE_ETCD_BACKUP_RESTORE_VERSION' and new sha256sum"
