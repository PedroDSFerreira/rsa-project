#!/bin/sh
# Block all peer MACs at startup so the ProximityManager controls connectivity from the start
if [ -n "$PEER_MACS" ]; then
    for mac in $(echo "$PEER_MACS" | tr ',' ' '); do
        block "$mac" 2>/dev/null || true
    done
fi
exec /entrypoint.sh "$@"
