"""HelloBoard with a read-only NetworkManager snapshot from the Pi."""
import json
import time
from pathlib import Path

from authentication import SystemAuthenticator
from werkzeug.security import check_password_hash
from host_platform import DashboardController
from network import NetworkError, split_escaped

class DashboardAuthenticator(SystemAuthenticator):
    def check_password(self, password):
        stored = (Path.home() / ".helloboard-password-hash").read_text().strip()
        return check_password_hash(stored, password)


class PiWifi(DashboardController):
    def __init__(self, path, interface):
        super().__init__(dict(snapshot=True, available=True, manage=False, ap=False, interface=interface,
                              reason="宿主机 Wi-Fi 只读。"))
        self.path = path

    def snapshot(self):
        try:
            return self.read_snapshot()
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise NetworkError("无法读取宿主机 Wi-Fi 状态。") from error

    def read_snapshot(self):
        path = self.path
        if time.time() - path.stat().st_mtime > 90:
            raise NetworkError("树莓派 Wi-Fi 状态已过期。")
        data = json.loads(path.read_text())
        networks = {}
        for line in data["rows"].splitlines():
            fields = split_escaped(line)
            if len(fields) != 4 or not fields[1]:
                continue
            active, ssid, signal, security = fields
            item = dict(active=active == "*", ssid=ssid, signal=int(signal or 0),
                        security=security or "开放网络", supported=security in ("", "--") or ("WPA" in security and "802.1X" not in security))
            key = ssid, security
            if key not in networks or (item["active"], item["signal"]) > (networks[key]["active"], networks[key]["signal"]):
                networks[key] = item
        return sorted(networks.values(), key=lambda n: (not n["active"], -n["signal"])), data["address"]

    def scan(self):
        rows, _ = self.snapshot()
        return dict(networks=rows, warning="显示树莓派 NetworkManager 的最近扫描结果。")

    def public_status(self):
        status = super().public_status()
        try:
            rows, address = self.snapshot()
        except NetworkError as error:
            status["message"] = str(error)
            return status
        current = next((r for r in rows if r["active"]), {})
        status.update(phase="preview", mode="lan", connected=bool(address), address=address, ssid=current.get("ssid", ""))
        return status
