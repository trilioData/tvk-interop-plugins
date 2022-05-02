#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC2154
echo "release tvk-quickstart package:" "$release_tvk_quickstart"
# shellcheck disable=SC2154
echo "release cleanup package:" "$release_cleanup"

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
goreleaser_yaml=$SRC_ROOT/.goreleaser.yml

if [[ $release_tvk_quickstart == true || $release_cleanup == true ]]; then

  echo '  extra_files:' >>"$goreleaser_yaml"

  if [[ $release_tvk_quickstart == true ]]; then
    echo "adding tvk-quickstart packages to goreleaser.yml"
    echo '    - glob: build/tvk-quickstart/tvk-quickstart.tar.gz
    - glob: build/tvk-quickstart/tvk-quickstart-sha256.txt' >>"$goreleaser_yaml"
  fi

  if [[ $release_cleanup == true ]]; then
    echo "adding cleanup packages to goreleaser.yml"
    echo '    - glob: build/cleanup/cleanup.tar.gz
    - glob: build/cleanup/cleanup-sha256.txt' >>"$goreleaser_yaml"
  fi

fi

echo "updated $goreleaser_yaml"
cat "$goreleaser_yaml"
