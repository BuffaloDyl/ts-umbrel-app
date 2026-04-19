import os

import requests
from flask import Flask, Response, jsonify

app = Flask(__name__)

UPSTREAM_BASE = os.environ.get("WIDGET_UPSTREAM_BASE", "http://host.docker.internal:9739").rstrip("/")
WIDGET_TIMEOUT = float(os.environ.get("WIDGET_PROXY_TIMEOUT", "5"))


def proxy_widget(path: str):
    upstream_url = f"{UPSTREAM_BASE}{path}"
    try:
        upstream = requests.get(upstream_url, timeout=WIDGET_TIMEOUT)
    except requests.RequestException as exc:
        return jsonify({"error": f"Widget upstream request failed: {exc}"}), 502

    content_type = upstream.headers.get("content-type", "application/json")
    return Response(upstream.content, status=upstream.status_code, content_type=content_type)


@app.route("/api/local/widgets/tunnel-status", methods=["GET"])
def tunnel_status_widget():
    return proxy_widget("/api/local/widgets/tunnel-status")


@app.route("/api/local/widgets/tunnel-overview", methods=["GET"])
def tunnel_overview_widget():
    return proxy_widget("/api/local/widgets/tunnel-overview")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "upstream": UPSTREAM_BASE})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9739)
