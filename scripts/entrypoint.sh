#!/bin/bash
set -e

echo "Starting Tunnelsats v3 (Umbrel App)..."

# Ensure we have docker socket access (for testing/prod)
if [ ! -S /var/run/docker.sock ]; then
    echo "ERROR: /var/run/docker.sock not mounted. Cannot determine LND/CLN IPs."
    sleep 30
    exit 1
fi

get_container_ip() {
    local container_name=$1
    curl -s --unix-socket /var/run/docker.sock "http://localhost/containers/json?all=1" | \
    jq -r ".[] | select(.Names[] | contains(\"$container_name\")) | .NetworkSettings.Networks[].IPAddress" | grep -v "null" | head -n 1
}

# Wait for at least one node to be present (Umbrel race condition mitigation)
MAX_RETRIES=30
RETRY_COUNT=0
LND_IP=""
CLN_IP=""

echo "Querying Docker API for Lightning Node IPs..."
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    LND_IP=$(get_container_ip "lightning_lnd_1")
    CLN_IP=$(get_container_ip "lightning_core-lightning_1")
    
    if [ -n "$LND_IP" ] || [ -n "$CLN_IP" ]; then
        break
    fi
    echo "Waiting for LND or CLN containers to initialize... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT+1))
done

echo "Target Node IPs - LND: ${LND_IP:-None}, CLN: ${CLN_IP:-None}"

CONFIG_FILE=$(find /data -name "tunnelsats*.conf" -type f | head -n 1)
if [ -z "$CONFIG_FILE" ]; then
    echo "ERROR: No Wireguard configuration found in /data. Please place your config file there."
    sleep 30
    exit 1
fi

echo "Using config: $CONFIG_FILE"
mkdir -p /etc/wireguard
cp "$CONFIG_FILE" "/etc/wireguard/tunnelsatsv2.conf"
WG_IFACE="tunnelsatsv2"

# 1. Spin up wireguard
wg-quick up "$WG_IFACE" || { echo "ERROR: wg-quick failed"; sleep 30; exit 1; }

# 2. Add Routing Tables and Policy Routing
# 51820 is standard Tunnelsats table
# Add policy rules for target IPs connecting them strictly to the VPN table
for ip in $LND_IP $CLN_IP; do
    if [ -n "$ip" ]; then
        echo "Applying killswitch and routing for container IP: $ip"
        ip rule add from "$ip" table 51820 2>/dev/null || true
    fi
done

# Native Killswitch: Route default to VPN. If VPN goes down, fall back to blackhole metric 3.
ip route add default dev "$WG_IFACE" metric 2 table 51820 || true
ip route add blackhole default metric 3 table 51820 || true

# Clean up trap
cleanup() {
    echo "Received SIGTERM. Shutting down Tunnelsats..."
    for ip in $LND_IP $CLN_IP; do
        if [ -n "$ip" ]; then
            ip rule del from "$ip" table 51820 2>/dev/null || true
        fi
    done
    wg-quick down "$WG_IFACE" 2>/dev/null || true
    exit 0
}

trap 'cleanup' SIGTERM

# Keep container alive
echo "Tunnelsats is running and protecting target IPs."
# wait command to block script and listen to trap
sleep infinity & 
wait $!
