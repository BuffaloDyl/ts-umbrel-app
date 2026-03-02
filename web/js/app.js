// State
let pollInterval;
let activePaymentHash = null;
let purchaseMode = "buy"; // "buy" or "renew"
// Initialization
document.addEventListener("DOMContentLoaded", () => {
    fetchStatus();
    fetchServers();
});

// UI Routing
function switchTab(tabId) {
    document.querySelectorAll('main > section').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('nav > button').forEach(el => {
        el.classList.remove('tab-active', 'font-bold');
        el.classList.add('text-gray-400');
    });

    document.getElementById(`view-${tabId}`).classList.remove('hidden');
    const btn = document.getElementById(`tab-${tabId}`);
    btn.classList.add('tab-active');
    btn.classList.remove('text-gray-400');
}

// 1. Fetch Local Status
async function fetchStatus() {
    try {
        const res = await fetch('/api/local/status');
        const data = await res.json();

        // Update Header Badge
        const badge = document.getElementById('statusBadge');
        if (data.wg_status === 'Connected') {
            badge.className = "px-4 py-2 rounded-full font-bold text-sm bg-green-900/50 text-tsgreen border border-green-700";
            badge.innerText = "Tunnel Active";
            document.getElementById('txt-wg-status').className = "font-mono text-tsgreen font-bold";
        } else {
            badge.className = "px-4 py-2 rounded-full font-bold text-sm bg-red-900/50 text-red-500 border border-red-700";
            badge.innerText = "Tunnel Down";
            document.getElementById('txt-wg-status').className = "font-mono text-red-500 font-bold";
        }

        // Update Dashboard Text
        document.getElementById('txt-wg-status').innerText = data.wg_status;
        const pk = data.wg_pubkey || "Not available";
        document.getElementById('txt-pubkey').innerText = pk;

        // Setup pubkey for renewal
        document.getElementById('renew-pubkey').value = pk;

        let confs = data.configs_found.length > 0 ? data.configs_found.join(", ") : "None Detected";
        document.getElementById('txt-configs').innerText = confs;

        document.getElementById('txt-lnd-ip').innerText = data.lnd_ip || "Not Detected";
        document.getElementById('txt-cln-ip').innerText = data.cln_ip || "Not Detected";

    } catch (e) {
        console.error("Failed to fetch status", e);
    }
}

// 2. Fetch Servers
async function fetchServers() {
    try {
        const res = await fetch('/api/servers');
        const servers = await res.json();

        const selBuy = document.getElementById('buy-server-select');
        const selRenew = document.getElementById('renew-server-select');

        selBuy.innerHTML = "";
        selRenew.innerHTML = "";

        servers.forEach(s => {
            let opt1 = document.createElement('option');
            opt1.value = s.id;
            opt1.innerText = `${s.country} - ${s.city} (Port: ${s.wireguardPort})`;
            selBuy.appendChild(opt1);

            let opt2 = document.createElement('option');
            opt2.value = s.id;
            opt2.innerText = `${s.country} - ${s.city} (Port: ${s.wireguardPort})`;
            selRenew.appendChild(opt2);
        });
    } catch (e) { }
}

// Purchase / Renew Mode Switch (Removed, handled by tabs now)

// Initialize QRCodes
let qrBuy = null;
let qrRenew = null;

function renderQR(mode, text) {
    const boxId = `qr-placeholder-${mode}`;
    const box = document.getElementById(boxId);
    box.innerHTML = ""; // Clear placeholder

    if (mode === 'buy') {
        if (!qrBuy) qrBuy = new QRCode(box, { width: 192, height: 192 });
        qrBuy.makeCode(text);
    } else {
        if (!qrRenew) qrRenew = new QRCode(box, { width: 192, height: 192 });
        qrRenew.makeCode(text);
    }
}

// 3. Purchase Flow
async function createSub(mode) {
    const serverId = document.getElementById(`${mode}-server-select`).value;
    const duration = parseInt(document.getElementById(`${mode}-duration-select`).value);

    // Save purchase mode globally for polling
    purchaseMode = mode;

    if (!serverId) return;

    // Helper for ui errors
    function displayPurchaseError(msg) {
        let errEl = document.getElementById(`purchase-error-${mode}`);
        if (!errEl) {
            errEl = document.createElement('p');
            errEl.id = `purchase-error-${mode}`;
            errEl.className = 'text-red-500 font-bold text-center mt-2';
            const container = document.getElementById(`btn-create-${mode}`).parentNode;
            container.appendChild(errEl);
        }
        errEl.innerText = msg;
    }

    const oldErr = document.getElementById(`purchase-error-${mode}`);
    if (oldErr) oldErr.remove();

    document.getElementById(`btn-create-${mode}`).innerText = "Loading...";
    document.getElementById(`btn-create-${mode}`).disabled = true;

    try {
        let endpoint = '/api/subscription/create';
        let payload = { serverId, duration, referralCode: null };

        if (mode === 'renew') {
            endpoint = '/api/subscription/renew';
            const wgPublicKey = document.getElementById('renew-pubkey').value;
            payload = { serverId, duration, wgPublicKey };
            if (!wgPublicKey || wgPublicKey === "Not available") {
                displayPurchaseError("Cannot renew without an active public key from a connected VPN.");
                document.getElementById(`btn-create-${mode}`).innerText = "Generate Renewal Invoice";
                document.getElementById(`btn-create-${mode}`).disabled = false;
                return;
            }
        }

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.paymentHash && data.invoice) {
            activePaymentHash = data.paymentHash;
            document.getElementById(`invoice-bolt11-${mode}`).value = data.invoice;
            document.getElementById(`pay-link-${mode}`).href = `lightning:${data.invoice}`;

            renderQR(mode, data.invoice);
            document.getElementById(`invoice-box-${mode}`).classList.remove('hidden');

            // Start Polling
            pollInterval = setInterval(pollPayment, 3000);
        } else if (data.message) {
            displayPurchaseError(data.message);
        }
    } catch (e) {
        displayPurchaseError("Error creating subscription: " + e.message);
    } finally {
        document.getElementById(`btn-create-${mode}`).innerText = mode === 'renew' ? "Generate Renewal Invoice" : "Generate Lightning Invoice";
        document.getElementById(`btn-create-${mode}`).disabled = false;
    }
}

async function pollPayment() {
    if (!activePaymentHash) return;

    try {
        const res = await fetch(`/api/subscription/${activePaymentHash}`);
        const data = await res.json();

        if (data.status === 'PAID') {
            clearInterval(pollInterval);
            const invoiceBox = document.getElementById(`invoice-box-${purchaseMode}`);
            invoiceBox.innerHTML = ''; // Clear content

            if (purchaseMode === 'buy') {
                const h3 = document.createElement('h3');
                h3.className = 'text-tsgreen font-bold text-center mb-2';
                h3.textContent = 'Payment Received!';

                const p = document.createElement('p');
                p.className = 'text-sm text-gray-300 text-center mb-4';
                p.textContent = 'Proceed to the Install tab to finalize your setup.';

                const button = document.createElement('button');
                button.className = 'mt-4 w-full bg-tsgreen hover:bg-cyan-500 text-gray-900 font-bold py-2 px-6 rounded transition shadow-lg';
                button.textContent = 'Proceed to Installation';
                button.onclick = () => {
                    document.getElementById('pending-install-section').classList.remove('hidden');
                    switchTab('import');
                };

                invoiceBox.append(h3, p, button);
            } else {
                const h3 = document.createElement('h3');
                h3.className = 'text-tsgreen font-bold text-center mb-2';
                h3.textContent = 'Renewal Successful!';

                const p = document.createElement('p');
                p.className = 'text-sm text-gray-300 text-center mb-4';
                p.textContent = 'Your VPN subscription has been extended successfully. No restarts required.';

                const button = document.createElement('button');
                button.className = 'mt-4 w-full bg-tsyellow hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition shadow-lg';
                button.textContent = 'Return to Dashboard';
                button.onclick = () => switchTab('dashboard');

                invoiceBox.append(h3, p, button);
            }
        }
    } catch (e) { }
}

async function claimSubscription(mode) {
    let btnInstall = null;
    if (mode === 'import') {
        btnInstall = document.getElementById('btn-claim-install');
        btnInstall.disabled = true;
        btnInstall.innerText = "Installing...";
    }

    try {
        const res = await fetch('/api/subscription/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paymentHash: activePaymentHash, referralCode: null })
        });

        const invoiceBox = document.getElementById(`invoice-box-${mode}`);
        invoiceBox.innerHTML = '';

        if (res.ok) {
            const configMsg = await configureNode();

            const h3 = document.createElement('h3');
            h3.className = 'text-tsgreen font-bold text-center mb-2';
            h3.textContent = 'Installation Complete!';

            const p1 = document.createElement('p');
            p1.className = 'text-sm text-gray-300 text-center mb-2';
            p1.textContent = 'Your VPN configuration has been securely stored.';

            const p2 = document.createElement('p');
            p2.className = 'text-xs text-tsyellow text-center mb-4';
            p2.textContent = configMsg;

            const button = document.createElement('button');
            button.className = 'mt-4 w-full bg-tsyellow hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition shadow-lg';
            button.textContent = 'Restart Apps & Tunnel';
            button.onclick = () => {
                restartTunnel();
                document.getElementById('pending-install-section').classList.add('hidden');
                activePaymentHash = null;
                switchTab('dashboard');
            };

            if (btnInstall) btnInstall.classList.add('hidden'); // Hide the install button now
            invoiceBox.append(h3, p1, p2, button);
        } else {
            const h3 = document.createElement('h3');
            h3.className = 'text-red-500 font-bold text-center mb-2';
            h3.textContent = 'Provisioning Error';

            const p = document.createElement('p');
            p.className = 'text-sm text-gray-300 text-center';
            p.textContent = 'Payment was successful, but config provisioning failed.';

            invoiceBox.append(h3, p);
            if (btnInstall) {
                btnInstall.disabled = false;
                btnInstall.innerText = "Retry Installation";
            }
        }
    } catch (e) {
        if (btnInstall) {
            btnInstall.disabled = false;
            btnInstall.innerText = "Retry Installation";
        }
    }
}

async function configureNode() {
    try {
        const res = await fetch('/api/local/configure-node', { method: 'POST' });
        const data = await res.json();

        let msg = "";
        if (data.lnd && data.cln) msg = "LND and CLN were auto-configured!";
        else if (data.lnd) msg = "LND was auto-configured! Please restart LND via UI.";
        else if (data.cln) msg = "CLN was auto-configured! Please restart CLN via UI.";
        else msg = "Auto-config unavailable due to Umbrel permissions. Please follow the manual setup guide.";

        return msg;
    } catch (e) {
        return "Auto-config unavailable. Please configure manually.";
    }
}

// 4. Import Config
async function importConfig() {
    const txt = document.getElementById('config-text').value;
    const msg = document.getElementById('import-msg');

    msg.innerText = "Importing...";
    msg.className = "text-center mt-4 text-sm text-gray-400";

    try {
        const formData = new FormData();
        formData.append('config_text', txt);

        const res = await fetch('/api/local/upload-config', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (res.ok) {
            const configMsg = await configureNode();
            msg.innerText = `Config imported successfully! ${configMsg}`;
            msg.className = "text-center mt-4 text-sm font-bold text-tsgreen";
            setTimeout(() => {
                restartTunnel();
                switchTab('dashboard');
            }, 3000);
        } else {
            msg.innerText = data.error || "Import failed.";
            msg.className = "text-center mt-4 text-sm font-bold text-red-500";
        }
    } catch (e) {
        msg.innerText = e.message;
        msg.className = "text-center mt-4 text-sm font-bold text-red-500";
    }
}

async function restartTunnel() {
    try {
        await fetch('/api/local/restart', { method: 'POST' });
        // The container entrypoint will catch the trigger file, and restart `wg-quick`
        setTimeout(fetchStatus, 3000);
    } catch (e) { }
}

async function restoreNode() {
    const btn = document.getElementById('btn-restore');
    const msg = document.getElementById('restore-msg');

    btn.disabled = true;
    btn.innerText = "Restoring Defaults...";
    msg.innerText = "";

    try {
        const res = await fetch('/api/local/restore-node', { method: 'POST' });
        const data = await res.json();

        const messages = [];
        if (data.lnd) messages.push("LND config removed.");
        if (data.cln) messages.push("CLN config reverted.");
        if (data.configs_cleaned) messages.push("VPN configs deleted.");

        let text = `Cleanup results: ${messages.length > 0 ? messages.join(' ') : 'No modifications found.'}`;

        msg.innerText = text;
        msg.className = "text-center mt-6 text-sm font-bold text-tsgreen";

        // Wait and then send a restart to wireguard just in case
        setTimeout(() => {
            fetch('/api/local/restart', { method: 'POST' });
            setTimeout(fetchStatus, 3000);
        }, 3000);

    } catch (e) {
        msg.innerText = "Failed to restore: " + e.message;
        msg.className = "text-center mt-6 text-sm font-bold text-red-500";
    } finally {
        btn.disabled = false;
        btn.innerText = "Restore Node Networking";
    }
}
