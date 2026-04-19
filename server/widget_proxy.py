import json
import os
import re
import socket
import subprocess
from datetime import datetime

import requests
from flask import Flask, jsonify

app = Flask(__name__)

DATA_DIR = "/data"
META_FILE = "tunnelsats-meta.json"
STATE_FILE = "/data/tunnelsats-state.json"
DOCKER_SOCK = "/var/run/docker.sock"
LND_CONFIG_PATH = "/lightning-data/lnd/lnd.conf"
CLN_CONFIG_PATH = "/lightning-data/cln/config"
CLN_RPC_PATH = "/lightning-data/cln/lightning-rpc"
CLN_RPC_TIMEOUT = 5
LIGHTNING_WIDGET_PORT = 3006
LIGHTNING_WIDGET_TIMEOUT = 5
LIGHTNING_STATS_PATH = "/v1/lnd/widgets/lightning-stats"
LND_CONTAINER_PATTERN = r"^lightning[_-]lnd[_-]\d+$"
LND_MIDDLEWARE_PATTERN = r"^lightning[_-]app[_-]\d+$"
CLN_CONTAINER_PATTERN = r"(^|[_-])(core-lightning|clightning|lightningd)([_-]|$)"


def read_json_file(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (IOError, OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def read_tunnelsats_metadata():
    return read_json_file(os.path.join(DATA_DIR, META_FILE))


def read_dataplane_state():
    defaults = {
        "target_impl": "",
        "vpn_active": False,
    }
    defaults.update(read_json_file(STATE_FILE))
    return defaults


def routing_flag_from_config(path, prefixes):
    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as conf_fp:
            for line in conf_fp:
                stripped = line.lstrip()
                if any(stripped.startswith(prefix) for prefix in prefixes):
                    return True
    except (IOError, OSError):
        return False

    return False


def docker_api(path):
    if not os.path.exists(DOCKER_SOCK):
        return None

    try:
        out = subprocess.check_output(
            ["curl", "-sS", "--fail", "--unix-socket", DOCKER_SOCK, f"http://localhost{path}"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return json.loads(out.decode("utf-8"))
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError, TimeoutError, OSError):
        return None


def container_ip_by_match(pattern, containers=None):
    if containers is None:
        containers = docker_api("/containers/json?all=0")
    if not containers:
        return ""

    for item in containers:
        if not isinstance(item, dict):
            continue
        names = item.get("Names")
        if not isinstance(names, list):
            continue
        for name in names:
            clean = str(name).lstrip("/")
            if re.search(pattern, clean):
                network_settings = item.get("NetworkSettings")
                if isinstance(network_settings, dict):
                    networks = network_settings.get("Networks")
                    if isinstance(networks, dict):
                        for network_data in networks.values():
                            if isinstance(network_data, dict):
                                ip = str(network_data.get("IPAddress", "")).strip()
                                if ip:
                                    return ip
    return ""


def container_ids_by_match(pattern, containers=None):
    if containers is None:
        containers = docker_api("/containers/json?all=0")
    if not containers:
        return []

    ids = []
    for item in containers:
        if not isinstance(item, dict):
            continue
        names = item.get("Names", [])
        for name in names:
            clean = str(name).lstrip("/")
            if re.search(pattern, clean):
                ids.append(item.get("Id", ""))
                break
    return ids


def get_lightning_widget_base_url():
    containers = docker_api("/containers/json?all=0") or []
    lightning_ip = container_ip_by_match(LND_MIDDLEWARE_PATTERN, containers=containers)
    if lightning_ip:
        return f"http://{lightning_ip}:{LIGHTNING_WIDGET_PORT}"
    return ""


def fetch_lightning_stats_widget_data():
    base_url = get_lightning_widget_base_url()
    if not base_url:
        raise ValueError("LND middleware container IP not found")

    response = requests.get(
        f"{base_url}{LIGHTNING_STATS_PATH}",
        timeout=LIGHTNING_WIDGET_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Lightning stats widget returned a non-object payload")
    return payload


def extract_lightning_stats_counts(widget_data):
    peers = "-"
    channels = "-"

    if isinstance(widget_data, dict) and widget_data.get("type") == "four-stats":
        items = widget_data.get("items")
        if isinstance(items, list):
            if len(items) > 0 and isinstance(items[0], dict):
                peers = str(items[0].get("text", "-")).strip() or "-"
            if len(items) > 1 and isinstance(items[1], dict):
                channels = str(items[1].get("text", "-")).strip() or "-"

    return peers, channels


def fetch_cln_counts():
    message = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getinfo", "params": {}})
        + "\n\n"
    ).encode("utf-8")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as rpc_socket:
        rpc_socket.settimeout(CLN_RPC_TIMEOUT)
        rpc_socket.connect(CLN_RPC_PATH)
        rpc_socket.sendall(message)

        payload = None
        response_bytes = b""
        while True:
            chunk = rpc_socket.recv(65536)
            if not chunk:
                break
            response_bytes += chunk
            try:
                payload = json.loads(response_bytes.decode("utf-8"))
                break
            except json.JSONDecodeError:
                continue

    if not isinstance(payload, dict):
        raise ValueError("CLN getinfo returned an invalid payload")

    if payload.get("error"):
        raise ValueError(f"CLN getinfo returned an error: {payload['error']}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("CLN getinfo returned a non-object result")

    peers = str(result.get("num_peers", "-")).strip() or "-"
    channels = str(result.get("num_active_channels", "-")).strip() or "-"
    return peers, channels


def fetch_tunnel_lightning_counts(target_impl):
    if str(target_impl or "").strip().lower() == "cln":
        return fetch_cln_counts()
    return extract_lightning_stats_counts(fetch_lightning_stats_widget_data())


def collect_tunnel_widget_state():
    containers = docker_api("/containers/json?all=0") or []
    meta = read_tunnelsats_metadata()
    dataplane = read_dataplane_state()
    peers = "-"
    active_channels = "-"

    try:
        peers, active_channels = fetch_tunnel_lightning_counts(dataplane.get("target_impl", ""))
    except (OSError, requests.RequestException, ValueError):
        pass

    return {
        "vpn_active": bool(dataplane.get("vpn_active")),
        "lnd_detected": bool(container_ids_by_match(LND_CONTAINER_PATTERN, containers=containers)),
        "cln_detected": bool(container_ids_by_match(CLN_CONTAINER_PATTERN, containers=containers)),
        "lnd_routing_active": routing_flag_from_config(LND_CONFIG_PATH, ("externalhosts=",)),
        "cln_routing_active": routing_flag_from_config(CLN_CONFIG_PATH, ("announce-addr=",)),
        "server_domain": str(meta.get("serverDomain", "")),
        "expires_at": str(meta.get("expiresAt", "")),
        "target_impl": str(dataplane.get("target_impl", "")),
        "peers": peers,
        "active_channels": active_channels,
    }


def get_tunnel_widget_summary(status_data):
    lnd_routing_active = bool(status_data.get("lnd_routing_active"))
    cln_routing_active = bool(status_data.get("cln_routing_active"))
    lnd_detected = bool(status_data.get("lnd_detected"))
    cln_detected = bool(status_data.get("cln_detected"))
    target_impl = str(status_data.get("target_impl", "")).strip().lower()

    if lnd_routing_active or target_impl == "lnd" or lnd_detected:
        node = "LND"
    elif cln_routing_active or target_impl == "cln" or cln_detected:
        node = "CLN"
    else:
        node = "None"

    if status_data.get("vpn_active") and (lnd_routing_active or cln_routing_active):
        tunnel = "🟢"
    elif status_data.get("vpn_active"):
        tunnel = "🟡"
    else:
        tunnel = "🔴"

    return {
        "node": node,
        "peers": str(status_data.get("peers", "-")).strip() or "-",
        "channels": str(status_data.get("active_channels", "-")).strip() or "-",
        "tunnel": tunnel,
    }


def build_tunnel_status_widget(status_data):
    summary = get_tunnel_widget_summary(status_data)
    return {
        "type": "three-stats",
        "link": "",
        "refresh": "5s",
        "items": [
            {"subtext": "Peers", "text": summary["peers"]},
            {"subtext": "Channels", "text": summary["channels"]},
            {"subtext": "Tunnel", "text": summary["tunnel"]},
        ],
    }


def format_tunnel_widget_expiration(expires_at):
    value = str(expires_at or "").strip()
    if not value:
        return "N/A"

    try:
        expiry_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return expiry_dt.strftime("%b %d %Y").replace(" 0", " ")
    except (ValueError, TypeError):
        if "T" in value:
            fallback = value.split("T", 1)[0].strip()
            return fallback or "N/A"
        return value


def build_tunnel_overview_widget(status_data):
    summary = get_tunnel_widget_summary(status_data)
    routing_protected = bool(status_data.get("vpn_active")) and (
        bool(status_data.get("lnd_routing_active")) or bool(status_data.get("cln_routing_active"))
    )

    return {
        "type": "four-stats",
        "link": "",
        "refresh": "5s",
        "items": [
            {"title": "Tunnel", "text": "🟢" if status_data.get("vpn_active") else "🔴"},
            {"title": "Protected", "text": "🟢" if routing_protected else "🔴"},
            {"title": "Expires", "text": format_tunnel_widget_expiration(status_data.get("expires_at"))},
            {"title": "Node", "text": summary["node"]},
        ],
    }


@app.route("/api/local/widgets/tunnel-status", methods=["GET"])
def tunnel_status_widget():
    return jsonify(build_tunnel_status_widget(collect_tunnel_widget_state()))


@app.route("/api/local/widgets/tunnel-overview", methods=["GET"])
def tunnel_overview_widget():
    return jsonify(build_tunnel_overview_widget(collect_tunnel_widget_state()))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9739)
