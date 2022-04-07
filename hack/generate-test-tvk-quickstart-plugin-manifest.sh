#!/usr/bin/env bash

set -e -o pipefail

set -x
echo >&2 "Creating TVK_Quickstart plugin manifest yaml"

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

tvk_quickstart_yaml="tvk-quickstart.yaml"
cp .krew/$tvk_quickstart_yaml $build_dir/$tvk_quickstart_yaml

tvk_quickstart_yaml=$build_dir/$tvk_quickstart_yaml

tar_checksum="$(awk '{print $1}' $build_dir/tvk-quickstart-sha256.txt)"
sed -i "s/TVK_QUICKSTART_TAR_CHECKSUM/${tar_checksum}/g" $tvk_quickstart_yaml
# shellcheck disable=SC2154
sed -i "s/TVK_QUICKSTART_VERSION/$git_version/g" $tvk_quickstart_yaml

echo >&2 "Written out $tvk_quickstart_yaml"
