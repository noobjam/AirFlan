#!/usr/bin/env sh
set -eu

CONTAINER_NAME="${AIRFLAN_POSTGRES_CONTAINER:-airflan-postgres}"
VOLUME_NAME="${AIRFLAN_POSTGRES_VOLUME:-airflan-postgres-data}"
POSTGRES_IMAGE="${AIRFLAN_POSTGRES_IMAGE:-docker.io/library/postgres:16}"
POSTGRES_PORT="${AIRFLAN_POSTGRES_PORT:-5432}"
POSTGRES_USER="${AIRFLAN_POSTGRES_USER:-airflan}"
POSTGRES_PASSWORD="${AIRFLAN_POSTGRES_PASSWORD:-airflan}"
POSTGRES_DB="${AIRFLAN_POSTGRES_DB:-airflan}"

if [ -n "${AIRFLAN_CONTAINER_RUNTIME:-}" ]; then
    RUNTIME="$AIRFLAN_CONTAINER_RUNTIME"
elif command -v podman >/dev/null 2>&1; then
    RUNTIME="podman"
elif command -v docker >/dev/null 2>&1; then
    RUNTIME="docker"
else
    printf '%s\n' "Neither podman nor docker was found on PATH." >&2
    exit 127
fi

case "${1:-start}" in
    start)
        "$RUNTIME" volume inspect "$VOLUME_NAME" >/dev/null 2>&1 || "$RUNTIME" volume create "$VOLUME_NAME"
        "$RUNTIME" run \
            --replace \
            --name "$CONTAINER_NAME" \
            -p "${POSTGRES_PORT}:5432" \
            -e POSTGRES_USER="$POSTGRES_USER" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e POSTGRES_DB="$POSTGRES_DB" \
            -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
            -d "$POSTGRES_IMAGE"
        printf '%s\n' "AIRFLAN_DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
        ;;
    stop)
        "$RUNTIME" stop "$CONTAINER_NAME"
        ;;
    logs)
        "$RUNTIME" logs -f "$CONTAINER_NAME"
        ;;
    status)
        "$RUNTIME" ps --filter "name=${CONTAINER_NAME}"
        ;;
    reset)
        "$RUNTIME" rm -f "$CONTAINER_NAME" 2>/dev/null || true
        "$RUNTIME" volume rm -f "$VOLUME_NAME"
        ;;
    *)
        printf '%s\n' "Usage: $0 [start|stop|logs|status|reset]" >&2
        exit 2
        ;;
esac
