#!/bin/bash
set -e

envsubst < .env.example > .env

exec python3 ./run.py
