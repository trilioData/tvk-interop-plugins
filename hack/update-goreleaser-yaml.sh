#!/usr/bin/env bash

set -euo pipefail

# shellcheck disable=SC2154
echo "release tvk-oneclick package:" "$release_tvk_oneclick"

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
goreleaser_yaml=$SRC_ROOT/.goreleaser.yml

if [[ $release_tvk_oneclick == true ]]; then

  echo '  extra_files:' >>"$goreleaser_yaml"

  if [[ $release_tvk_oneclick == true ]]; then
    echo "adding tvk-oneclick packages to goreleaser.yml"
    echo '    - glob: build/tvk-oneclick/tvk-oneclick.tar.gz
    - glob: build/tvk-oneclick/tvk-oneclick-sha256.txt' >>"$goreleaser_yaml"
  fi

fi

echo "updated $goreleaser_yaml"
cat "$goreleaser_yaml"
