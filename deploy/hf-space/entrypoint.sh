#!/usr/bin/env bash
# Container start: migrate, then serve.
#
# `set -e` is the whole point of the file. A migration that fails must stop the container
# rather than let uvicorn start against a schema no revision describes — which is the exact
# failure S11 spent an afternoon on, arriving as "Something went wrong on our side" at every
# upload instead of as a failed deploy.
set -euo pipefail

echo "stylelab: applying migrations"
alembic upgrade head

# Migrations at container start are correct for **one** instance and wrong for many: two
# replicas starting together race on the same revision. A Space is one instance, so this is
# the right trade here and would not be on a platform that scales out. Said in
# docs/DEPLOYMENT.md rather than assumed.

echo "stylelab: starting api on ${PORT:-7860}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-7860}" \
    --proxy-headers \
    --forwarded-allow-ips='*'

# `--forwarded-allow-ips='*'` trusts the forwarded client address from any hop, which is
# correct **only** because a Space is reachable exclusively through Hugging Face's proxy. It
# is what makes the per-address session rate limit see real callers rather than one shared
# bucket for the internet (app/services/ratelimit.py). On a host reachable directly it would
# be the opposite: an attacker sets their own address and the limiter has no floor.
