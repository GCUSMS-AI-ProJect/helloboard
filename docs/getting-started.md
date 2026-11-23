# Installation and operation

HelloBoard requires Python 3.10+. Linux is the primary platform. Dashboard-only mode monitors the host without taking over WiFi.

## Linux

On Raspberry Pi OS, Debian, and Ubuntu, run the following to install and start a systemd service.

```bash
sudo apt update
sudo apt install git python3 python3-venv
git clone https://github.com/GCUSMS-AI-ProJect/helloboard.git
cd helloboard
sudo bash install.sh --start
```

Open `http://localhost` on the device or use its private IP from a device on the same network. Port 80 must be available unless you set a different port before starting. The app lives in `/opt/helloboard`, with `helloboard.service` enabled at boot. Run `sudo bash install.sh` without `--start` if you want to edit the settings before starting.

## Docker and other Linux environments without systemd

From a checkout with Python 3.10+ and `venv` installed, run the same installer.

```bash
bash install.sh --start
```

The installer uses `.venv/` in the checkout and runs HelloBoard in the foreground on port 8090. Use `bash start.sh` for subsequent launches. Use `bash install.sh --local --start` to select the foreground mode on a systemd host.

For a standalone image, build the included Dockerfile and use Docker’s restart policy. Publish port 8090 when creating the container. The full Raspberry Pi Docker deployment adds host Wi-Fi management and the Bash proxy panel over dedicated sockets. [Docker commands](../README.md#docker-image) · [Raspberry Pi Docker deployment](https://github.com/GCUSMS-AI-ProJect/hello_docker_pi)

## Environment variables

For a source-based systemd installation, edit `/etc/helloboard/helloboard.env` and run `sudo systemctl restart helloboard`. In a shell, export the variables before running `bash start.sh`. With Docker, pass them using `docker run -e` or `--env-file`. Explicit command-line flags take precedence, including flags preserved in an older systemd unit.

| Variable | Purpose |
| --- | --- |
| `HELLOBOARD_HOST` | Listen address, default `0.0.0.0`. |
| `HELLOBOARD_PORT` | Listen port, default `80` for a fresh system service or `8090` for shell and Docker. |
| `HELLOBOARD_AUTH_USER` | System login account used for authorization. |
| `HELLOBOARD_INTERFACE` | Wireless interface for the selected Wi-Fi backend. |
| `HELLOBOARD_CONFIG` | Absolute path to a writable Wi-Fi configuration file, when required by the backend. |
| `HELLOBOARD_BOOT_WIFI_WAIT` | Startup wait before the host Wi-Fi bridge opens the setup hotspot, in seconds. |
| `HELLOBOARD_PROXY_SOCKET` | Path to a separately provisioned Bash proxy worker socket. |

On a source systemd installation, keep writable Wi-Fi settings within `/opt/helloboard`, as required by the unit’s filesystem restrictions. In Docker, use a writable mounted directory for Wi-Fi settings you want to keep when recreating the container.

## Optional WiFi management

WiFi management requires NetworkManager, root privileges, and a managed wireless adapter. Creating a hotspot also requires AP support. On Debian / Ubuntu, the required system packages are `network-manager` and `dnsmasq-base`; check your existing network setup before changing managers.

Use `sudo bash install.sh --with-wifi --start` on a new native installation to enable network management. Starting this service applies the saved mode. A Docker deployment that uses the host Wi-Fi control service should keep using its bridge for that adapter. If no configuration exists, the default is an open hotspot named `hellosms` at `192.168.11.17`; set a hotspot password before routine use. Keep wired or local-console access available during initial setup.

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

This update command is for systemd source installations. Updates preserve saved WiFi configuration, service arguments, and startup settings. They restart the service; WiFi-enabled deployments reapply the saved network mode and may briefly disconnect.

In an existing container or a local checkout, stop the foreground app, pull the source changes, and rerun `bash install.sh --start`. Rebuild and recreate standalone Docker images to update them.

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
