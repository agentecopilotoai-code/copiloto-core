#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://localhost:8000/v1/health | python3 -m json.tool
curl -fsS -H 'Authorization: Bearer' http://localhost:8000/openapi.json >/dev/null
