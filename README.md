<h1 align="center">HelloBoard</h1>

<p align="center">A browser dashboard for monitoring Linux devices and managing their Wi-Fi.</p>

<p align="center">
  <a href="#raspberry-pi-os-debian-or-ubuntu"><img src="https://img.shields.io/badge/Raspberry%20Pi-OS-A22846?style=flat-square" alt="Raspberry Pi OS"></a>
  <a href="#platform-support"><img src="https://img.shields.io/badge/Platform-Linux-374151?style=flat-square" alt="Linux"></a>
  <a href="#docker-image"><img src="https://img.shields.io/badge/Deployment-Docker-1D63ED?style=flat-square" alt="Docker deployment"></a>
  <a href="docs/getting-started.md"><img src="https://img.shields.io/badge/Python-3.10%2B-306998?style=flat-square" alt="Python 3.10 or later"></a>
  <a href="#wi-fi-management"><img src="https://img.shields.io/badge/Network-Wi--Fi-146A55?style=flat-square" alt="Wi-Fi management"></a>
  <a href="#bash-proxy"><img src="https://img.shields.io/badge/Proxy-Bash-51408D?style=flat-square" alt="Bash proxy"></a>
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#screenshots">Screenshots</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#docker-image">Docker</a> ·
  <a href="docs/project-guide.md">中文指南</a>
</p>

[![Full HelloBoard system dashboard in light mode with populated charts, device information, and a process table](docs/images/system-light.png)](docs/images/system-light.png)

## Features

| Feature | What you can do |
| --- | --- |
| System monitoring | Track CPU, memory, disk, network traffic, uptime, and hardware metrics where available. Live charts share in-memory history across browsers. |
| Process management | Search and sort processes by CPU or memory. On supported Linux deployments, verify your system account to terminate selected processes. |
| Wi-Fi and device hotspot | Scan for networks, reconnect to saved networks, and switch between Wi-Fi and hotspot mode on compatible NetworkManager devices. |
| Setup hotspot | On first startup with host Wi-Fi control, give NetworkManager 60 seconds by default to join a network. If it cannot connect in time, open the setup hotspot and retain the saved configuration. |
| Bash proxy | Configure HTTP, HTTPS, or SOCKS5, set a direct-connection list and test timeout, then test or save the host user's Bash settings. Requires the host proxy service. |
| Responsive interface | Use the dashboard on desktop or mobile in English or Chinese, with light and dark themes and compact or spacious layouts. |

HelloBoard uses Flask, Waitress, and browser-native HTML, CSS, and JavaScript. It serves its fonts and icons locally. See the benchmark summary for the sampling design and historical memory and transfer measurements. [Benchmark summary](docs/benchmarks.md)

## Screenshots

### System dashboard · dark theme

[![Full HelloBoard system dashboard in dark mode with CPU, memory, and network traffic charts](docs/images/system-dark.png)](docs/images/system-dark.png)

### Wi-Fi management

![Wi-Fi management page with saved connection settings and nearby networks](docs/images/wifi-desktop.png)

### Device hotspot

![Device hotspot settings with an example network name and address](docs/images/wifi-hotspot.png)

### Bash proxy

![Bash proxy page with protocol, host, port, bypass list, timeout, and test controls](docs/images/proxy-settings.png)

**Test connection** checks the proxy without writing any settings. Saving an enabled proxy checks connectivity through `http://ipinfo.io` before updating the host user's Bash. Enter comma-separated hosts or addresses in the bypass list to connect to them directly.

### Mobile layout

<img src="docs/images/wifi-mobile.png" alt="Wi-Fi configuration on a phone" width="360">

The screenshots use example device, chart, network, and proxy data.

## Quick start

HelloBoard uses the same source on Raspberry Pi OS, Debian, Ubuntu, and in Linux containers. Run the installer from your checkout. It detects a systemd host or installs into a local Python virtual environment.

### Raspberry Pi OS, Debian, or Ubuntu

```bash
sudo apt install git python3 python3-venv
git clone https://github.com/GCUSMS-AI-ProJect/helloboard.git
cd helloboard
sudo bash install.sh --start
```

Open the device’s IP in a browser. The service starts at boot and listens on port 80 by default. Its environment file is `/etc/helloboard/helloboard.env`. To run in your terminal instead, use `bash install.sh --local --start` and open port 8090.

To enable native Wi-Fi management on a new installation, use `sudo bash install.sh --with-wifi --start`. This requires NetworkManager and a managed adapter. Hotspot mode also requires AP support. The service applies the saved network mode at startup. [Installation, settings, and updates](docs/getting-started.md)

For local discovery on Debian or Ubuntu, install `avahi-daemon` and run `sudo python3 tools/enable_local_name.py`. Open `http://helloboard.local` from an mDNS-capable client on the same network. [Local discovery guide](docs/operations.md)

### In an existing Linux container

With Python 3.10+ and `venv` available, run `bash install.sh --start` inside the checkout. The installer uses `.venv/` and starts HelloBoard in the foreground on port 8090. Use `bash start.sh` for subsequent starts. Publish the port when creating the container.

## Docker image

Run these commands on the Docker host to build a standalone dashboard with automatic restart.

```bash
docker build -t helloboard .
docker run -d --name helloboard --restart unless-stopped -p 127.0.0.1:8090:8090 helloboard
```

Open `http://localhost:8090` on the Docker host. Pass `-e HELLOBOARD_PORT=8080` and publish `127.0.0.1:8090:8080` to use port 8080 inside the container.

For read-only host Wi-Fi status, run the snapshot exporter on the host every 15 seconds:

```bash
python3 tools/export_wifi_snapshot.py ./wifi-cache --interface wlan0
```

Mount the snapshot directory when starting the container:

```bash
docker run --rm -p 127.0.0.1:8091:8090 \
  -v "$PWD/wifi-cache:/run/helloboard-wifi:ro" \
  helloboard --wifi-snapshot /run/helloboard-wifi/latest.json --interface wlan0
```

Replace `wlan0` with the host adapter in both commands and open `http://localhost:8091`. Snapshots expire after 90 seconds. For optional snapshot-mode panel login, mount a private Werkzeug password hash at `/home/helloboard/.helloboard-password-hash` and grant the container user read access.

For a Raspberry Pi container with host Wi-Fi management and the Bash proxy panel, use the deployment repository. It provisions the host services that the container calls. [Raspberry Pi Docker deployment](https://github.com/GCUSMS-AI-ProJect/hello_docker_pi)

## Platform support

Linux is the primary platform. Available metrics and controls depend on system permissions and hardware. The Windows scripts enable monitoring, with physical Windows-host verification still pending. Use HelloBoard on a trusted local network and keep device credentials in the local configuration. [Supported platforms and permissions](docs/getting-started.md)

## Documentation

- [Installation, updates, and troubleshooting](docs/getting-started.md)
- [Benchmark summary](docs/benchmarks.md)
- [UI design prompt (Chinese)](PROMPT.md)
- [Project guide and installation (Chinese)](docs/project-guide.md)
- [Deployment and local discovery (Chinese)](docs/operations.md)
- [Performance measurements (Chinese)](docs/performance.md)
- [Offline Ubuntu amd64 package (Chinese)](docs/deb.md)
- [Font sources and licenses](static/fonts/SOURCES.md)

## Feedback

Include your OS, architecture, Python version, commit, and reproduction steps when reporting an issue. Remove private information from logs and screenshots. [GitHub Issues](https://github.com/GCUSMS-AI-ProJect/helloboard/issues)

## License

HelloBoard's own code currently has no project-level license. Third-party assets and runtimes retain their respective licenses. [Fonts](static/fonts/SOURCES.md) · [Lucide icons](static/lucide-LICENSE.txt) · [Bundled runtime notices](packaging/deb/runtime-licenses)
