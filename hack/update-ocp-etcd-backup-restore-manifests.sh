#!/bin/bash

set -e -o pipefail

if [[ -z "${OCP_ETCD_BACKUP_RESTORE_VERSION}" ]]; then
  echo >&2 "OCP_ETCD_BACKUP_RESTORE_VERSION (required) is not set"
  exit 1
else
  echo "OCP_ETCD_BACKUP_RESTORE_VERSION is set to ${OCP_ETCD_BACKUP_RESTORE_VERSION}"
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
# shellcheck disable=SC2164
cd "$SRC_ROOT"

plugins_dir="$SRC_ROOT"/plugins
build_dir="$SRC_ROOT"/build
template_manifest_dir="$SRC_ROOT"/.krew
ocp_etcd_backup_restore_yaml="ocp-etcd-backup-restore.yaml"
ocp_etcd_backup_restore_template_manifest=$template_manifest_dir/$ocp_etcd_backup_restore_yaml

mkdir -p "${build_dir}"

# shellcheck disable=SC2086
cp "$ocp_etcd_backup_restore_template_manifest" $build_dir/$ocp_etcd_backup_restore_yaml
ocp_etcd_backup_restore_template_manifest=$build_dir/$ocp_etcd_backup_restore_yaml

repoURL=$(git config --get remote.origin.url)

#For Linux
ocpetcdbackuprestoreSha256File="ocp-etcd-backup-restore-Linux-sha256.txt"

ocpetcdbackuprestoreSha256URI="$repoURL/releases/download/${OCP_ETCD_BACKUP_RESTORE_VERSION}/$ocpetcdbackuprestoreSha256File"
ocpetcdbackuprestoreSha256FilePath=$build_dir/$ocpetcdbackuprestoreSha256File

curl -fsSL "$ocpetcdbackuprestoreSha256URI" >"${ocpetcdbackuprestoreSha256FilePath}"

if [ -s "${ocpetcdbackuprestoreSha256FilePath}" ]; then
  echo "File ${ocpetcdbackuprestoreSha256FilePath} successfully downloaded and contains data"
else
  echo "File ${ocpetcdbackuprestoreSha256FilePath} does not contain any data. Exiting..."
  exit 1
fi

ocp_etcd_backup_restore_sha=$(awk '{print $1}' "$ocpetcdbackuprestoreSha256FilePath")

sed -i "s/OCP_ETCD_BACKUP_RESTORE_VERSION/$OCP_ETCD_BACKUP_RESTORE_VERSION/g" "$ocp_etcd_backup_restore_template_manifest"
sed -i "s/OCP_ETCD_BACKUP_RESTORE_LINUX_TAR_CHECKSUM/$ocp_etcd_backup_restore_sha/g" "$ocp_etcd_backup_restore_template_manifest"

#For MAC users

ocpetcdbackuprestoreSha256File="ocp-etcd-backup-restore-macOS-sha256.txt"

ocpetcdbackuprestoreSha256URI="$repoURL/releases/download/${OCP_ETCD_BACKUP_RESTORE_VERSION}/$ocpetcdbackuprestoreSha256File"
ocpetcdbackuprestoreSha256FilePath=$build_dir/$ocpetcdbackuprestoreSha256File

curl -fsSL "$ocpetcdbackuprestoreSha256URI" >"${ocpetcdbackuprestoreSha256FilePath}"

if [ -s "${ocpetcdbackuprestoreSha256FilePath}" ]; then
  echo "File ${ocpetcdbackuprestoreSha256FilePath} successfully downloaded and contains data"
else
  echo "File ${ocpetcdbackuprestoreSha256FilePath} does not contain any data. Exiting..."
  exit 1
fi

ocp_etcd_backup_restore_sha=$(awk '{print $1}' "$ocpetcdbackuprestoreSha256FilePath")

sed -i "s/OCP_ETCD_BACKUP_RESTORE_MAC_TAR_CHECKSUM/$ocp_etcd_backup_restore_sha/g" "$ocp_etcd_backup_restore_template_manifest"

cp "$build_dir"/$ocp_etcd_backup_restore_yaml "$plugins_dir"/$ocp_etcd_backup_restore_yaml
echo >&2 "Updated ocp-etcd-backup-restore plugin manifest '$ocp_etcd_backup_restore_template_manifest' with 'version=$OCP_ETCD_BACKUP_RESTORE_VERSION' and new sha256sum"
