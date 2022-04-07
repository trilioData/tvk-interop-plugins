#!/usr/bin/env bash

set -euo pipefail

set -x
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"

# create tvk-quickstart tar package
tvk_quickstart_tar_archive="tvk-quickstart.tar.gz"
echo >&2 "Creating ${tvk_quickstart_tar_archive} archive."

cd "$SRC_ROOT"
build_dir="build"
mkdir $build_dir
cp -r tools/tvk-quickstart $build_dir
cp LICENSE.md $build_dir/tvk-quickstart
cd $build_dir
mv tvk-quickstart/tvk-quickstart.sh tvk-quickstart/tvk-quickstart

# consistent timestamps for files in build dir to ensure consistent checksums
while IFS= read -r -d $'\0' f; do
  echo "modifying atime/mtime for $f"
  TZ=UTC touch -at "0001010000" "$f"
  TZ=UTC touch -mt "0001010000" "$f"
done < <(find . -print0)

tar -cvzf ${tvk_quickstart_tar_archive} tvk-quickstart/
echo >&2 "Created ${tvk_quickstart_tar_archive} archive successfully"

# create tvk-quickstart tar sha256 file
echo >&2 "Compute sha256 of ${tvk_quickstart_tar_archive} archive."

checksum_cmd="shasum -a 256"
if hash sha256sum 2>/dev/null; then
  checksum_cmd="sha256sum"
fi

tvk_quickstart_sha256_file=tvk-quickstart-sha256.txt
"${checksum_cmd[@]}" "${tvk_quickstart_tar_archive}" >$tvk_quickstart_sha256_file
echo >&2 "Successfully written sha256 of ${tvk_quickstart_tar_archive} into $tvk_quickstart_sha256_file"
