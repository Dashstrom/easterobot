#!/bin/sh
if [ ! -f /data/config.yml ]
then
  uv run easterobot generate /data
fi
uv run easterobot run --config /data/config.yml --env
