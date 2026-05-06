#!/usr/bin/env sh
set -eu

CONTAINER_NAME="${AIRFLAN_POSTGRES_CONTAINER:-airflan-postgres}"
VOLUME_NAME="${AIRFLAN_POSTGRES_VOLUME:-airflan-postgres-data}"
POSTGRES_IMAGE="${AIRFLAN_POSTGRES_IMAGE:-docker.io/library/postgres:16}"
POSTGRES_PORT="${AIRFLAN_POSTGRES_PORT:-5432}"
POSTGRES_USER="${AIRFLAN_POSTGRES_USER:-airflan}"
POSTGRES_PASSWORD="${AIRFLAN_POSTGRES_PASSWORD:-airflan}"
POSTGRES_DB="${AIRFLAN_POSTGRES_DB:-airflan}"

case "${1:-start}" in
    start)
        podman volume exists "$VOLUME_NAME" || podman volume create "$VOLUME_NAME"
        podman run \
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
        podman stop "$CONTAINER_NAME"
        ;;
    logs)
        podman logs -f "$CONTAINER_NAME"
        ;;
    status)
        podman ps --filter "name=${CONTAINER_NAME}"
        ;;
    reset)
        podman rm -f "$CONTAINER_NAME" 2>/dev/null || true
        podman volume rm -f "$VOLUME_NAME"
        ;;
    *)
        printf '%s\n' "Usage: $0 [start|stop|logs|status|reset]" >&2
        exit 2
        ;;
esac
