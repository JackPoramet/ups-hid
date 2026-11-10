#!/bin/bash
set -e

target=${1:?Log directory path is required}
if [ -d "$target" ]; then
    exit 0
fi
if [ -e "$target" ] || [ -L "$target" ]; then
    echo "ERROR: Log path exists and is not a directory: $target" >&2
    exit 1
fi

umask 022
mkdir -p -m 0755 -- "$target"
