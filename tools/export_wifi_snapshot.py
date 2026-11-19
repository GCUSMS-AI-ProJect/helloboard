import argparse
import json
from tempfile import NamedTemporaryFile
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description="Export cached Wi-Fi status for a read-only container mount")
parser.add_argument("directory", type=Path)
parser.add_argument("--interface", default="wlan0")
args = parser.parse_args()
cache = args.directory
cache.mkdir(parents=True, exist_ok=True)
def query(*args):
    return subprocess.check_output(["nmcli", *args], text=True, timeout=5)

rows = query("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
             "ifname", args.interface, "--rescan", "no")
addresses = query("-g", "IP4.ADDRESS", "dev", "show", args.interface).splitlines()
with NamedTemporaryFile(mode="w", dir=cache, delete=False) as stream:
    json.dump(dict(rows=rows, address=addresses[0].split("/")[0] if addresses else ""), stream)
tmp = Path(stream.name)
tmp.chmod(0o644)
tmp.replace(cache / "latest.json")
