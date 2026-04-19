import json
import os
import sys
from unittest.mock import patch

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
import widget_proxy


def test_widget_proxy_and_app_share_dataplane_state_path():
    assert app_module.STATE_FILE == "/data/tunnelsats-state.json"
    assert widget_proxy.STATE_FILE == app_module.STATE_FILE


def test_tunnel_status_widget_reports_protected_lnd_server():
    status_payload = {
        "vpn_active": True,
        "lnd_routing_active": True,
        "cln_routing_active": False,
        "lnd_detected": True,
        "cln_detected": False,
        "target_impl": "lnd",
        "server_domain": "de2.tunnelsats.com",
        "expires_at": "2026-05-04T19:06:14.000Z",
        "peers": "5",
        "active_channels": "3",
    }

    with widget_proxy.app.test_client() as client, patch(
        "widget_proxy.collect_tunnel_widget_state", return_value=status_payload
    ):
        res = client.get("/api/local/widgets/tunnel-status")

    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["type"] == "three-stats"
    assert data["refresh"] == "5s"
    assert data["items"][0] == {"subtext": "Peers", "text": "5"}
    assert data["items"][1] == {"subtext": "Channels", "text": "3"}
    assert data["items"][2] == {"subtext": "Tunnel", "text": "🟢"}


def test_tunnel_overview_widget_reports_status_protection_and_expiry():
    status_payload = {
        "vpn_active": True,
        "lnd_routing_active": True,
        "cln_routing_active": False,
        "lnd_detected": True,
        "cln_detected": False,
        "target_impl": "lnd",
        "server_domain": "us3.tunnelsats.com",
        "expires_at": "2026-05-04T19:06:14.000Z",
        "peers": "5",
        "active_channels": "3",
    }

    with widget_proxy.app.test_client() as client, patch(
        "widget_proxy.collect_tunnel_widget_state", return_value=status_payload
    ):
        res = client.get("/api/local/widgets/tunnel-overview")

    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["type"] == "four-stats"
    assert data["refresh"] == "5s"
    assert data["items"][0] == {"title": "Tunnel", "text": "🟢"}
    assert data["items"][1] == {"title": "Protected", "text": "🟢"}
    assert data["items"][2] == {"title": "Expires", "text": "May 4 2026"}
    assert data["items"][3] == {"title": "Node", "text": "LND"}


def test_tunnel_overview_widget_reports_unprotected_without_expiry():
    status_payload = {
        "vpn_active": False,
        "lnd_routing_active": True,
        "cln_routing_active": False,
        "lnd_detected": True,
        "cln_detected": False,
        "target_impl": "lnd",
        "server_domain": "us3.tunnelsats.com",
        "expires_at": "",
        "peers": "5",
        "active_channels": "3",
    }

    with widget_proxy.app.test_client() as client, patch(
        "widget_proxy.collect_tunnel_widget_state", return_value=status_payload
    ):
        res = client.get("/api/local/widgets/tunnel-overview")

    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["items"][0] == {"title": "Tunnel", "text": "🔴"}
    assert data["items"][1] == {"title": "Protected", "text": "🔴"}
    assert data["items"][2] == {"title": "Expires", "text": "N/A"}
    assert data["items"][3] == {"title": "Node", "text": "LND"}


def test_manifest_includes_widget_proxy_endpoints():
    manifest_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "tunnelsats", "umbrel-app.yml")
    )
    with open(manifest_path, "r", encoding="utf-8") as fp:
        manifest = yaml.safe_load(fp)

    widgets = manifest.get("widgets", [])
    assert [widget["id"] for widget in widgets] == ["tunnel-status", "tunnel-overview"]
    assert widgets[0]["endpoint"] == "widget-proxy:9739/api/local/widgets/tunnel-status"
    assert widgets[1]["endpoint"] == "widget-proxy:9739/api/local/widgets/tunnel-overview"
