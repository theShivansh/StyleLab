# STYLELAB API — Hugging Face Space (Docker SDK)
#
# Built and run by Hugging Face from the Space repository, whose root is the build context.
# `deploy/hf-space/prepare.py` assembles that repository from this one; it copies `apps/api`
# and this file, and nothing else — the web app is Vercel's problem and has no business in a
# Python image.
#
# Three things about Spaces shape this file:
#
# 1. **The container does not run as root.** Spaces run the image as UID 1000, so every path
#    the application writes to has to be owned by that user at build time. A container that
#    only discovers this at the first upload fails with a permission error on somebody's
#    photograph.
# 2. **The filesystem is ephemeral** on the free tier. Uploaded images and a SQLite database
#    live only as long as the container. See the README in this directory — it is the reason
#    `DATABASE_URL` should point somewhere else.
# 3. **Port 7860**, matching `app_port` in the Space card.

FROM python:3.11-slim

# `build-essential` is here for the source distributions in the CrewAI tree that have no
# manylinux wheel. It is a build cost rather than an image cost only if the install is in a
# separate stage — not worth the complexity here, where the image is rebuilt rarely and the
# 200MB matters less than a build that fails on a missing compiler after eight minutes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# UID 1000, because that is what Spaces runs as. Named `app` rather than reusing `nobody` so
# a shell in the container has a home directory to write into.
RUN useradd --create-home --uid 1000 app
USER app
ENV HOME=/home/app \
    PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /home/app/api

# Dependencies before source, so an edit to a route does not reinstall CrewAI. The two are
# copied separately for that reason alone.
COPY --chown=app:app apps/api/pyproject.toml ./pyproject.toml
COPY --chown=app:app apps/api/app ./app
RUN pip install --user .

COPY --chown=app:app apps/api/alembic.ini ./alembic.ini
COPY --chown=app:app apps/api/migrations ./migrations
COPY --chown=app:app deploy/hf-space/entrypoint.sh /home/app/entrypoint.sh
# Set here rather than relied on from git. The Space repository is written by
# `huggingface_hub.upload_folder`, which does not carry a file's executable bit — so a mode
# that is correct in this repository arrives at 644 and the container fails to start with
# "permission denied" on a file that looks right in every diff.
RUN chmod +x /home/app/entrypoint.sh

# Where uploads land. Created and owned at build time: a Space that discovers the permission
# problem at the first upload has already taken the user's photograph and lost it.
#
# On the free tier this directory does **not** survive a restart (blocker B20). Point
# `STORAGE_ROOT` at `/data/uploads` instead if the Space has persistent storage attached.
RUN mkdir -p /home/app/var/uploads
ENV STORAGE_ROOT=/home/app/var/uploads

# Matches `app_port` in the Space card. Spaces ignores EXPOSE and reads that instead, so the
# two are kept the same by hand and this line is documentation for a human.
EXPOSE 7860

# Liveness only, and deliberately not the provider — an outage is reported through the error
# envelope, not by making the container look dead (docs/DEPLOYMENT.md).
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:7860/health || exit 1

ENTRYPOINT ["/home/app/entrypoint.sh"]
