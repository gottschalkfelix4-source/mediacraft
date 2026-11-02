#!/bin/sh
# Runs MediaCraft as PUID:PGID (linuxserver.io convention) so files in /data get the right owner.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
umask "${UMASK:-002}"

if [ "$(id -u)" = "0" ]; then
    if ! getent group "$PGID" >/dev/null 2>&1; then
        groupadd -o -g "$PGID" mediacraft
    fi
    if ! getent passwd "$PUID" >/dev/null 2>&1; then
        useradd -o -u "$PUID" -g "$PGID" -d /config -s /usr/sbin/nologin mediacraft
    fi
    chown -R "$PUID:$PGID" /config
    echo "MediaCraft startet als UID $PUID / GID $PGID (umask $(umask))"
    exec setpriv --reuid="$PUID" --regid="$PGID" --init-groups "$@"
fi

exec "$@"
