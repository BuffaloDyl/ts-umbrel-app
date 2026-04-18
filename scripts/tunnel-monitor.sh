#!/bin/bash
set -euo pipefail

WG_IFACE="${WG_IFACE:-tunnelsatsv2}"
STATE_FILE="${STATE_FILE:-/tmp/tunnelsats_state.json}"
LOG_PATH="${TUNNELSATS_MONITOR_LOG:-/data/tunnel-monitor.log}"
INTERVAL_SECONDS="${TUNNELSATS_MONITOR_INTERVAL:-60}"
STALE_SECONDS="${TUNNELSATS_MONITOR_STALE_SECONDS:-180}"
DETAIL_COOLDOWN_SECONDS="${TUNNELSATS_MONITOR_DETAIL_COOLDOWN:-300}"

LAST_DETAIL_EPOCH=0
LAST_STATUS=""

timestamp_utc() {
    date -u +%FT%TZ
}

log_line() {
    local level="$1"
    shift
    printf '%s [%s] %s\n' "$(timestamp_utc)" "${level}" "$*" >> "${LOG_PATH}"
}

state_value() {
    local jq_expr="$1"
    if [ ! -f "${STATE_FILE}" ]; then
        echo ""
        return 0
    fi

    jq -r "${jq_expr} // empty" "${STATE_FILE}" 2>/dev/null || true
}

dump_snapshot() {
    local reason="$1"
    {
        printf '%s [SNAPSHOT] reason=%s\n' "$(timestamp_utc)" "${reason}"
        echo "--- wg show ${WG_IFACE} ---"
        wg show "${WG_IFACE}" 2>&1 || true
        echo "--- ip addr show dev ${WG_IFACE} ---"
        ip addr show dev "${WG_IFACE}" 2>&1 || true
        echo "--- ip rule show ---"
        ip rule show 2>&1 || true
        echo "--- ip route show table 51820 ---"
        ip route show table 51820 2>&1 || true
        echo "--- iptables -t nat -S ---"
        iptables -t nat -S 2>&1 || true
        echo "--- iptables -S FORWARD ---"
        iptables -S FORWARD 2>&1 || true
        echo "--- dataplane state ---"
        cat "${STATE_FILE}" 2>&1 || true
        echo "--- end snapshot ---"
    } >> "${LOG_PATH}"
}

monitor_once() {
    local now_epoch
    now_epoch="$(date +%s)"

    if ! wg show "${WG_IFACE}" >/dev/null 2>&1; then
        log_line "WARN" "status=missing interface=${WG_IFACE}"
        if [ "${LAST_STATUS}" != "missing" ] || [ $((now_epoch - LAST_DETAIL_EPOCH)) -ge ${DETAIL_COOLDOWN_SECONDS} ]; then
            dump_snapshot "missing"
            LAST_DETAIL_EPOCH="${now_epoch}"
        fi
        LAST_STATUS="missing"
        return 0
    fi

    local latest_line endpoint_line transfer_line
    latest_line="$(wg show "${WG_IFACE}" latest-handshakes 2>/dev/null | head -n 1 || true)"
    endpoint_line="$(wg show "${WG_IFACE}" endpoints 2>/dev/null | head -n 1 || true)"
    transfer_line="$(wg show "${WG_IFACE}" transfer 2>/dev/null | head -n 1 || true)"

    local latest_handshake endpoint rx_bytes tx_bytes
    latest_handshake="$(echo "${latest_line}" | awk '{print $2}')"
    endpoint="$(echo "${endpoint_line}" | awk '{print $2}')"
    rx_bytes="$(echo "${transfer_line}" | awk '{print $2}')"
    tx_bytes="$(echo "${transfer_line}" | awk '{print $3}')"

    [ -n "${endpoint}" ] || endpoint="none"
    [ -n "${rx_bytes}" ] || rx_bytes="0"
    [ -n "${tx_bytes}" ] || tx_bytes="0"

    local status handshake_age
    status="connected"
    handshake_age="-1"

    if [[ ! "${latest_handshake}" =~ ^[0-9]+$ ]] || [ "${latest_handshake}" -le 0 ]; then
        status="no-handshake"
    else
        handshake_age=$((now_epoch - latest_handshake))
        if [ "${handshake_age}" -gt "${STALE_SECONDS}" ]; then
            status="stale"
        fi
    fi

    local target_impl forwarding_port rules_synced last_error
    target_impl="$(state_value '.target_impl')"
    forwarding_port="$(state_value '.forwarding_port')"
    rules_synced="$(state_value '.rules_synced')"
    last_error="$(state_value '.last_error')"

    log_line \
        "INFO" \
        "status=${status} handshake_age=${handshake_age} endpoint=${endpoint} rx_bytes=${rx_bytes} tx_bytes=${tx_bytes} target_impl=${target_impl:-unknown} forwarding_port=${forwarding_port:-unknown} rules_synced=${rules_synced:-unknown} last_error=${last_error:-none}"

    if [ "${status}" != "connected" ] && { [ "${LAST_STATUS}" != "${status}" ] || [ $((now_epoch - LAST_DETAIL_EPOCH)) -ge ${DETAIL_COOLDOWN_SECONDS} ]; }; then
        dump_snapshot "${status}"
        LAST_DETAIL_EPOCH="${now_epoch}"
    fi

    LAST_STATUS="${status}"
}

mkdir -p "$(dirname "${LOG_PATH}")"
touch "${LOG_PATH}"
log_line "INFO" "monitor_started interface=${WG_IFACE} interval=${INTERVAL_SECONDS}s stale_after=${STALE_SECONDS}s"

while true; do
    monitor_once
    sleep "${INTERVAL_SECONDS}"
done
