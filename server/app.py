import os
import time
import subprocess
import requests
import logging
import yaml
from ipaddress import ip_address, ip_network
from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__, static_folder="../web", static_url_path="")
# Umbrel uses an app-proxy, so request.remote_addr will be 127.0.0.1 unless we use ProxyFix to parse X-Forwarded-For.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)

TUNNELSATS_API_URL = "https://tunnelsats.com/api/public/v1"
DATA_DIR = "/data"

# Allow local loopback and all standard private subnets (RFC 1918) for LAN access
ALLOWED_NETWORKS = [
    ip_network('127.0.0.0/8'),
    ip_network('10.0.0.0/8'),
    ip_network('172.16.0.0/12'),
    ip_network('192.168.0.0/16')
]

@app.before_request
def restrict_local_api():
    if request.path.startswith('/api/local/'):
        remote_addr = request.remote_addr
        if remote_addr:
            try:
                ip_obj = ip_address(remote_addr)
                if not any(ip_obj in net for net in ALLOWED_NETWORKS):
                    app.logger.warning(f"Unauthorized access attempt to {request.path} from {remote_addr}")
                    abort(403)
            except ValueError:
                abort(403)
        else:
            abort(403)

def get_active_vpn_info():
    port = None
    dns = "vpn.tunnelsats.com" 
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".conf"):
                with open(os.path.join(DATA_DIR, f), "r") as c:
                    for line in c:
                        if "VPNPort" in line or "Port Forwarding" in line:
                            import re
                            m = re.search(r'\b(\d{4,5})\b', line)
                            if m:
                                port = m.group(1)
                        if "Endpoint" in line:
                            import re
                            m = re.search(r'Endpoint\s*=\s*([^:]+)', line)
                            if m and not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', m.group(1)):
                                dns = m.group(1).strip()
    return port, dns

# Proxy function to forward requests to the core Tunnelsats API
def proxy_request(method, endpoint, payload=None):
    url = f"{TUNNELSATS_API_URL}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            return jsonify({"error": "Unsupported method"}), 405
            
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.headers.items()
                   if name.lower() not in excluded_headers]
                   
        return (resp.content, resp.status_code, headers)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)

# --- API PROXY ROUTES ---

@app.route("/api/servers", methods=["GET"])
def get_servers():
    return proxy_request('GET', 'servers')

@app.route("/api/subscription/create", methods=["POST"])
def create_subscription():
    return proxy_request('POST', 'subscription/create', request.json)

@app.route("/api/subscription/<paymentHash>", methods=["GET"])
def check_subscription(paymentHash):
    return proxy_request('GET', f'subscription/{paymentHash}')

@app.route("/api/subscription/claim", methods=["POST"])
def claim_subscription():
    # If the claim was successful, we also want to intercept the config and save it
    url = f"{TUNNELSATS_API_URL}/subscription/claim"
    try:
        resp = requests.post(url, json=request.json, headers={"Content-Type": "application/json"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "wireguardConfig" in data and "server" in data:
                # Save config
                server_id = data["server"].get("id", "unknown")
                if os.path.exists(DATA_DIR):
                    for f in os.listdir(DATA_DIR):
                        if f.endswith(".conf"):
                            try: os.remove(os.path.join(DATA_DIR, f))
                            except: pass
                            
                config_path = os.path.join(DATA_DIR, f"tunnelsats-{server_id}.conf")
                with open(config_path, "w") as f:
                    f.write(data["wireguardConfig"])
        return (resp.content, resp.status_code, resp.headers.items())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/renew", methods=["POST"])
def renew_subscription():
    return proxy_request('POST', 'subscription/renew', request.json)

# --- LOCAL APP ROUTES ---

@app.route("/api/local/status", methods=["GET"])
def local_status():
    # Detect if WireGuard is running
    wg_status = "Disconnected"
    wg_ip = ""
    wg_pubkey = ""
    try:
        output = subprocess.check_output(["wg", "show", "tunnelsatsv2"], stderr=subprocess.STDOUT).decode("utf-8")
        if "interface: tunnelsatsv2" in output:
            wg_status = "Connected"
            for line in output.split("\n"):
                if line.strip().startswith("public key:"):
                    wg_pubkey = line.split(":", 1)[1].strip()
    except Exception:
        pass

    # Check for config files in /data
    configs = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith(".conf"):
                configs.append(f)

    # Check for LND and CLN IPs via docker socket
    lnd_ip = ""
    cln_ip = ""
    try:
        if os.path.exists("/var/run/docker.sock"):
            # Use dynamic filters to find the LND and CLN containers
            lnd_out = subprocess.check_output("docker ps -q --filter 'name=lnd|lightningd' | grep -v 'core-lightning' | head -n 1 | xargs -r docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'", shell=True, stderr=subprocess.DEVNULL)
            lnd_ip = lnd_out.decode().strip()
            cln_out = subprocess.check_output("docker ps -q --filter 'name=cln|lightning' | grep -v 'lnd' | head -n 1 | xargs -r docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'", shell=True, stderr=subprocess.DEVNULL)
            cln_ip = cln_out.decode().strip()
    except Exception as e:
        app.logger.error(f"Failed to fetch local status info: {e}")

    # Get version from manifest
    version = "v3.0.0" # Default
    try:
        manifest_path = os.path.join(os.path.dirname(__file__), "..", "umbrel-app.yml")
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                manifest = yaml.safe_load(f)
                version = f"v{manifest.get('version', '3.0.0')}"
    except Exception:
        pass

    return jsonify({
        "wg_status": wg_status,
        "wg_pubkey": wg_pubkey,
        "configs_found": configs,
        "lnd_ip": lnd_ip,
        "cln_ip": cln_ip,
        "version": version
    })

@app.route("/api/local/upload-config", methods=["POST"])
def upload_config():
    if "config" not in request.files and "config_text" not in request.form:
        return jsonify({"error": "No config provided"}), 400
        
    config_data = ""
    if "config" in request.files:
        file = request.files["config"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400
        config_data = file.read().decode("utf-8")
    else:
        config_data = request.form.get("config_text", "")
        
    if "[Interface]" not in config_data or "[Peer]" not in config_data:
        return jsonify({"error": "Invalid WireGuard configuration format"}), 400
        
    # Write to /data securely
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        else:
            for f in os.listdir(DATA_DIR):
                if f.endswith(".conf"):
                    try: os.remove(os.path.join(DATA_DIR, f))
                    except: pass
            
        config_path = os.path.join(DATA_DIR, "tunnelsats-imported.conf")
        with open(config_path, "w") as f:
            f.write(config_data)
            
        return jsonify({"success": True, "message": "Config imported successfully."})
    except Exception as e:
        return jsonify({"error": f"Failed to save config: {str(e)}"}), 500

@app.route("/api/local/restart", methods=["POST"])
def restart_tunnel():
    try:
        with open("/tmp/tunnelsats_restart_trigger", "w") as f:
            f.write("trigger")
        return jsonify({"success": True, "message": "Restarting tunnel..."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/local/configure-node", methods=["POST"])
def configure_node():
    port, dns = get_active_vpn_info()
    if not port:
        return jsonify({"error": "No VPN forwarding port found in config."}), 400
        
    lnd_success = False
    lnd_path = "/lightning-data/lnd/tunnelsats.conf"
    if os.path.exists("/lightning-data/lnd"):
        try:
            with open(lnd_path, "w") as f:
                f.write(f"[Application Options]\nexternalhosts={dns}:{port}\n\n[Tor]\ntor.streamisolation=false\ntor.skip-proxy-for-clearnet-targets=true\n")
            lnd_success = True
        except Exception as e:
            app.logger.error(f"Error configuring LND: {e}")

    cln_success = False
    cln_path = "/lightning-data/cln/config"
    if os.path.exists(cln_path):
        try:
            with open(cln_path, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                if not line.startswith("bind-addr=") and not line.startswith("announce-addr=") and not line.startswith("always-use-proxy="):
                    new_lines.append(line)
                    
            new_lines.append(f"bind-addr=0.0.0.0:9735\n")
            new_lines.append(f"announce-addr={dns}:{port}\n")
            new_lines.append(f"always-use-proxy=false\n")
            
            with open(cln_path, "w") as f:
                f.writelines(new_lines)
            cln_success = True
        except Exception as e:
            app.logger.error(f"Error configuring CLN: {e}")

    return jsonify({"lnd": lnd_success, "cln": cln_success, "port": port, "dns": dns})

@app.route("/api/local/restore-node", methods=["POST"])
def restore_node():
    lnd_success = False
    lnd_path = "/lightning-data/lnd/tunnelsats.conf"
    if os.path.exists(lnd_path):
        try:
            with open(lnd_path, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                if line.startswith("externalhosts=") or line.startswith("tor.skip-proxy-for-clearnet-targets="):
                    if not line.startswith("#"):
                        new_lines.append(f"#{line}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            with open(lnd_path, "w") as f:
                f.writelines(new_lines)
            lnd_success = True
        except Exception as e:
            app.logger.error(f"Error removing LND config: {e}")

    cln_success = False
    cln_path = "/lightning-data/cln/config"
    if os.path.exists(cln_path):
        try:
            with open(cln_path, "r") as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                if line.startswith("bind-addr=") or line.startswith("announce-addr=") or line.startswith("always-use-proxy="):
                    if not line.startswith("#"):
                        new_lines.append(f"#{line}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            with open(cln_path, "w") as f:
                f.writelines(new_lines)
            cln_success = True
        except Exception as e:
            app.logger.error(f"Error removing CLN config: {e}")

    configs_cleaned = False
    # DO NOT delete .conf files in DATA_DIR. 
    # The user paid for these VPN configs, and removing the App should preserve them as backups.

    return jsonify({"lnd": lnd_success, "cln": cln_success, "configs_cleaned": configs_cleaned})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9739)
