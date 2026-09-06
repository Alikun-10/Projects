#!/bin/sh
set -u

until pg_isready -q; do
    sleep 2
done

while true; do
    if ! psql \
        -v ON_ERROR_STOP=1 \
        -qAtc "SELECT cleanup_old_data();" \
        >/dev/null
    then
        echo "cleanup_old_data failed" >&2
    fi

    sleep 60
done
