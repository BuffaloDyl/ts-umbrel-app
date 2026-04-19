# TunnelSats Developer Guide (Umbrel 1.x)

This document explains the repository structure and workflow for the TunnelSats Umbrel application.

## Directory Structure

| Path | Purpose |
| :--- | :--- |
| `/` (Root) | Primary development workspace and source code (Server, Web, Scripts). |
| `tunnelsats/` | **Staging Area** for Umbrel Metadata (Manifests, Icons, Gallery). |
| `scripts/` | Tooling for verification, persistence testing, and synchronization. |
| `umbrel-apps/tunnelsats/` | **External Monorepo Target** for official submissions. |

## Single Source of Truth

*   **Docker Compose**: The canonical `docker-compose.yml` is located in `tunnelsats/docker-compose.yml`.
*   **Root Convenience Link**: The root `docker-compose.yml` is a symlink to `tunnelsats/docker-compose.yml` for local tooling compatibility.

## Networking Constraint

*   **Host Networking Is Mandatory**: The main `tunnelsats` service must keep `network_mode: "host"`. The WireGuard dataplane, routing rules, and firewall behavior depend on host-network semantics.
*   **Widgets Cannot Target the Host-Networked Service Directly**: Umbrel resolves widget endpoints by taking the hostname in `umbrel-app.yml`, treating it as a compose service name, then looking up that service's container IP. This breaks if the endpoint host is `127.0.0.1` or if the target service is host-networked.
*   **Widget Proxy Pattern**: `widget-proxy` exists specifically to satisfy Umbrel's widget fetch model. It stays on normal Docker networking and forwards `/api/local/widgets/*` to the main app at `host.docker.internal:9739`.
*   **Do Not Collapse the Services**: If widgets stop loading after networking edits, check `tunnelsats/umbrel-app.yml` endpoints and the `widget-proxy` service before touching host networking on the main app.

## Synchronization Workflow

### 1. Verification (Local/Remote)
Always verify your changes on a live Umbrel node before submitting to the monorepo.

For source changes under `server/`, `web/`, or `scripts/`, use the hot-patch workflow so the running
container actually receives the updated code:
```bash
dev@env:~/ts-umbrel-app$ scripts/sync.sh node
```

Only syncing `tunnelsats/` updates app-store metadata such as `umbrel-app.yml`, icons, and gallery assets.
That is not sufficient for backend route changes and can produce manifest/runtime mismatches such as widget
endpoints returning `404 NOT FOUND`.

### 2. Multi-Repo Release Automation (`promote`)
We utilize an automated release promotion workflow to maintain total parity between our local repository and the official `umbrel-apps` GitHub fork.

When a new version is ready:
1. Ensure `tunnelsats/umbrel-app.yml` contains the correct new `version: "x.y.z"`.
2. Ensure the Docker image is built and pushed to Docker Hub (`tunnelsats/ts-umbrel-app:vX.Y.Z`).
3. Run the automation:
```bash
npm run promote
# Under the hood, this executes: scripts/sync.sh promote
```

**The `promote` automation executes the following sequence:**
- **Discovery**: Extracts the version from `umbrel-app.yml`.
- **SHA256 Pinning**: Polls Docker Hub to fetch the official multi-arch digest index and pins it directly into `tunnelsats/docker-compose.yml`, ensuring production immutability.
- **Monorepo Synchronization**: Recursively forces synchronization (rsync) of the local `tunnelsats/` folder into the target `umbrel-apps` structure.
- **Hybrid Stripping**: Surgically strips our development absolute GitHub URLs (icons, gallery) from the target `umbrel-app.yml` to maintain Umbrel CDN-first submission protocol compliance.

> [!TIP]
> **Pre-Push Hook**: A Git pre-push hook intercepts pushes to `master` and prompts the developer to execute this promotion layer automatically before changes are pushed upstream.

## Important Files

- `scripts/test.sh persistence`: Verifies that configuration data survives Umbrel 1.x uninstallation.
- `tunnelsats/scripts/verify.sh dataplane`: Automated health check for local/remote installations (must be executed with `sudo`).
- `umbrel-app.yml`: Main Umbrel app manifest (located in `tunnelsats/`).
- `docs/widget-types.md`: Practical reference for the widget payload shapes we currently know how to build.

> [!IMPORTANT]
> **Data Persistence**: TunnelSats maps its data volume to a peer directory (`../tunnelsats-data`) on Umbrel to prevent data loss when the app is uninstalled via the App Manager. Do not change this mapping without consulting the persistence documentation.
