FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    wireguard-tools \
    iproute2 \
    iptables \
    nftables \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/ /app/scripts/
RUN chmod +x /app/scripts/*.sh

ENV WG_CONF_PATH="/data/tunnelsats*.conf"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
