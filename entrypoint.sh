#!/bin/sh
if [ ! -f /data/config.yml ]
then
  uv run --frozen easterobot generate /data
fi
uv run --frozen easterobot run --config /data/config.yml --env
