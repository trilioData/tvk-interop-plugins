#!/usr/bin/env bash

set -euo pipefail

# ensures s3cmd & yq utilities are installed on host machine

install_s3cmd_if_needed() {
  if hash s3cmd 2>/dev/null; then
    echo >&2 "using s3cmd from the host system and not reinstalling"
  else
    echo >&2 "s3mcd not detected in environment, installing..."

    sudo apt-get update && sudo apt-get install s3cmd
    s3cmd --version
    echo >&2 "installed s3cmd"
  fi
}

install_yq_if_needed() {

  if hash yq 2>/dev/null; then
    echo >&2 "using yq from the host system and not reinstalling"
  else
    echo >&2 "yq not detected in environment, installing..."

    local -r YQ_VERSION="v4.18.1"
    local -r BINARY=yq_linux_amd64
    wget https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/${BINARY} -O /usr/bin/yq &&
      chmod +x /usr/bin/yq
    yq -V
    echo >&2 "installed yq"
  fi
}

install_s3cmd_if_needed
install_yq_if_needed
