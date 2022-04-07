#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC2046
# shellcheck disable=SC2006
current_tag=$(git describe --abbrev=0 --tags)

# validate if current tag directly references the supplied commit, this check needed for goreleaser
git describe --exact-match --tags --match "$current_tag"

# shellcheck disable=SC2046
# shellcheck disable=SC2006
previous_tag=$(git tag --sort=-creatordate | grep -e "v[0-9].[0-9].[0-9]" | grep -v -e "$current_tag" -e "v*-alpha*" -e "v*-beta*" | head -n 1)
# use hard coded values if required
#current_tag=v0.0.6-main
#previous_tag=v0.0.5-dev

# if current tag is stable one, check its diff with last stable tag
if echo "$current_tag" | grep -w '^v[0-9].[0-9].[0-9]$'; then
  previous_tag=$(git tag --sort=-creatordate | grep -e "v[0-9].[0-9].[0-9]" | grep -v -e "$current_tag" -e "v*-alpha*" -e "v*-beta*" -e "v*-rc*" | head -n 1)
fi

echo "current_tag=$current_tag and previous_tag=$previous_tag"

echo "checking paths of modified files-"

tvk_quickstart_changed=false
rke_etcd_backup_restore_changed=false
ocp_etcd_backup_restore_changed=false

tools_dir="tools"
internal_dir="internal"
tvk_quickstart_dir="tvk-quickstart"
ocp_etcd_backup_restore="ocp_etcd_backup_plugin"
rke_etcd_backup_restore="rke_etcd_backup_plugin"

# shellcheck disable=SC2086
git diff --name-only $previous_tag $current_tag $tools_dir >files.txt
# shellcheck disable=SC2086
git diff --name-only $previous_tag $current_tag $internal_dir >>files.txt

count=$(wc -l <files.txt)
if [[ $count -eq 0 ]]; then
  echo "no plugin directory has been modified... skipping release"
  echo "::set-output name=create_release::false"
  exit
fi

echo "list of modified files-"
cat files.txt

while IFS= read -r file; do
  if [[ ($tvk_quickstart_changed == false) && ($file == $tools_dir/$tvk_quickstart_dir/*) ]]; then
    echo "tvk-quickstart related code changes have been detected"
    echo "::set-output name=release_tvk_quickstart::true"
    tvk_quickstart_changed=true
  fi

  if [[ ($ocp_etcd_backup_restore_changed == false) && ($file == $internal_dir/* || $file == $tools_dir/$ocp_etcd_backup_restore/*) ]]; then
    echo "ocp-etcd-backup-restore related code changes have been detected"
    echo "::set-output name=release_ocp_etcd_backup_restore::true"
    ocp_etcd_backup_restore_changed=true
  fi

  if [[ ($rke_etcd_backup_restore_changed == false) && ($file == $internal_dir/* || $file == $tools_dir/$rke_etcd_backup_restore/*) ]]; then
    echo "rke-etcd-backup-restore related code changes have been detected"
    echo "::set-output name=release_rke_etcd_backup_restore::true"
    rke_etcd_backup_restore_changed=true
  fi

done <files.txt

if [[ $rke_etcd_backup_restore_changed == true || $ocp_etcd_backup_restore_changed == true || $tvk_quickstart_changed == true ]]; then
  echo "Creating Release as files related to tvk-quickstart, ocp-etcd-backup-restore, rke-etcd-backup-restore  have been changed"
  echo "::set-output name=create_release::true"
fi

# use hard coded values if required for releasing specific plugin package
#echo "Creating release with user defined values"
#echo "::set-output name=create_release::true"
#echo "::set-output name=release_tvk_quickstart::true"
#echo "::set-output name=release_ocp_etcd_backup_restore::true"
#echo "::set-output name=release_rke_etcd_backup_restore::true"
