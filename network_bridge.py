import json
import socket
from network import NetworkError

class HostNetwork:
    def __init__(self, path, interface):
        self.path = str(path)
        self.interface = interface

    def call(self, action, **values):
        try:
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(85)
                client.connect(self.path)
                client.sendall(json.dumps(dict(action=action, **values)).encode() + b"\n")
                with client.makefile("rb") as stream:
                    reply = json.load(stream)
        except (OSError, ValueError) as error:
            raise NetworkError("无法访问宿主机 Wi-Fi 服务。") from error
        if "error" in reply:
            raise NetworkError(reply["error"])
        return reply["result"]

    def snapshot(self):
        return self.call("snapshot")

    def scan(self):
        return self.call("scan")

    def read_connection_password(self, connection_uuid):
        return self.call("password", uuid=connection_uuid)

    def activate(self, mode, config):
        return self.call("activate", config={**config, "mode": mode})
