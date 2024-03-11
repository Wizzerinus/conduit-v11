#!/usr/bin/env bash

cd /var/local/conduit-v11

if [ -f PIDlock ]; then
  exit 1
fi

source venv/bin/activate
python3 venv/bin/uvicorn --port 7554 --host 0.0.0.0 --workers 1 pyconduit.website.website:app
