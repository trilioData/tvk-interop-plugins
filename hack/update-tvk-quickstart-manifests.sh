#!/bin/bash

set -e -o pipefail

set -x
if [[ -z "${TVK_QUICKSTART_VERSION}" ]]; then
  echo >&2 "TVK_QUICKSTART_VERSION (required) is not set"
  exit 1
else
  echo "TVK_QUICKSTART_VERSION is set to ${TVK_QUICKSTART_VERSION}"
fi

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
# shellcheck disable=SC2164
cd "$SRC_ROOT"

plugins_dir="$SRC_ROOT"/plugins
build_dir="$SRC_ROOT"/build
template_manifest_dir="$SRC_ROOT"/.krew
tvk_quickstart_yaml="tvk-quickstart.yaml"
tvk_quickstart_template_manifest=$template_manifest_dir/$tvk_quickstart_yaml

mkdir -p "${build_dir}"

# shellcheck disable=SC2086
cp "$tvk_quickstart_template_manifest" $build_dir/$tvk_quickstart_yaml
tvk_quickstart_template_manifest=$build_dir/$tvk_quickstart_yaml

repoURL=$(git config --get remote.origin.url | sed 's/\.git$//')
tvkquickstartSha256File="tvk-quickstart-sha256.txt"

tvkquickstartSha256URI="$repoURL/releases/download/${TVK_QUICKSTART_VERSION}/$tvkquickstartSha256File"
tvkquickstartSha256FilePath=$build_dir/$tvkquickstartSha256File

curl -fsSL "$tvkquickstartSha256URI" >"${tvkquickstartSha256FilePath}"

if [ -s "${tvkquickstartSha256FilePath}" ]; then
  echo "File ${tvkquickstartSha256FilePath} successfully downloaded and contains data"
else
  echo "File ${tvkquickstartSha256FilePath} does not contain any data. Exiting..."
  exit 1
fi

tvk_quickstart_sha=$(awk '{print $1}' "$tvkquickstartSha256FilePath")

sed -i "s/TVK_QUICKSTART_VERSION/$TVK_QUICKSTART_VERSION/g" "$tvk_quickstart_template_manifest"
sed -i "s/TVK_QUICKSTART_TAR_CHECKSUM/$tvk_quickstart_sha/g" "$tvk_quickstart_template_manifest"

cp "$build_dir"/$tvk_quickstart_yaml "$plugins_dir"/$tvk_quickstart_yaml
echo >&2 "Updated tvk-quickstart plugin manifest '$tvk_quickstart_yaml' with 'version=$TVK_QUICKSTART_VERSION' and new sha256sum"
