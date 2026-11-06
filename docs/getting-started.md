# Installation and operation

HelloBoard requires Python 3.10+. Linux is the primary platform. Dashboard-only mode monitors the host without taking over WiFi.

## Linux

On Debian / Ubuntu, install the prerequisites:

```bash
sudo apt update
sudo apt install git python3 python3-venv
git clone https://github.com/GCUSMS-AI-ProJect/helloboard.git
cd helloboard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python wifi.py --dashboard-only
```

Open `http://localhost:8090`, or use the device's private IP from another device on the same network. Stop the foreground process with Ctrl+C before installing a service.

For a systemd service on port 80:

```bash
sudo bash install.sh
sudo systemctl enable --now helloboard
```

The installed program lives in `/opt/helloboard`. Port 80 must be available.

## Optional WiFi management

WiFi management requires NetworkManager, root privileges, and a managed wireless adapter. Creating a hotspot also requires AP support. On Debian / Ubuntu, the required system packages are `network-manager` and `dnsmasq-base`; check your existing network setup before changing managers.

Use `sudo bash install.sh --with-wifi` instead of the default installer when you intend to enable network management. Starting this service applies the saved mode. If no configuration exists, the default is an open hotspot named `hellosms` at `192.168.11.17`; set a hotspot password before routine use. Keep wired or local-console access available during initial setup.

WiFi configuration and saved credentials are stored in `/opt/helloboard/wifi.yaml`, with Linux permissions set to `0600`. Viewing passwords, changing the AP password, and terminating processes require system-account verification. Do not commit this configuration to Git.

## Optional local name

With the installed service running on port 80:

```bash
sudo apt install avahi-daemon
sudo python3 tools/enable_local_name.py
```

Open `http://helloboard.local` from an mDNS-capable client on the same local network, or after joining the device hotspot. Avahi follows interface address changes and starts on boot. Guest isolation, multicast filtering, VPNs, and duplicate device names can interfere with discovery; use the device IP if needed.

## Updates and service checks

From the source checkout:

```bash
git pull --ff-only
sudo bash update.sh
```

Updates preserve saved WiFi configuration, service arguments, and startup settings. They restart the service; WiFi-enabled deployments reapply the saved network mode and may briefly disconnect.

```bash
systemctl status helloboard
journalctl -u helloboard -n 50 --no-pager
sudo systemctl restart helloboard
sudo systemctl disable --now helloboard
```

If the page does not load, check service status, port conflicts, firewall rules, and the device's current IP. If WiFi controls are missing, check NetworkManager, adapter support, and whether the service is dashboard-only or in preview mode. Use this dashboard only on trusted local networks; do not expose it directly to the public internet.

## Windows

With Python 3.10+ installed, run these commands in PowerShell from the project directory:

```powershell
.\install.ps1
.\start.ps1
```

Open `http://localhost:8090`. Optional `install.ps1 -AutoStart` creates a task that starts the dashboard when the current user signs in. Windows supports monitoring only; WiFi management and process termination are unavailable. Physical Windows-host validation is still pending.

See the [deployment reference](operations.md) and [offline Ubuntu amd64 package guide](deb.md) for additional details (Chinese).
