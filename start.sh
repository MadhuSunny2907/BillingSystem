#!/usr/bin/env bash
gunicorn --bind 0.0.0.0:$PORT --timeout 180 app:app