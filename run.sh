#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [ ! -x .venv/bin/python ]; then
    echo "Run ./install.sh first." >&2
    exit 1
fi
exec .venv/bin/python -m plevel "$@"
