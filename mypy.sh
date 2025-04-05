#!/bin/zsh

filename=$1

if [ -z "$filename" ]; then
    echo "Usage: mypy.sh <filename>"
    exit 1
fi

mypy --check-untyped-defs --strict-equality "$filename"
