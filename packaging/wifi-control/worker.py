"""Handle one systemd socket connection on the host's configured adapter."""
import json
import sys
from configuration import validate_config
from network import NetworkManager, NetworkError

def dispatch(request, nm):
    action = request["action"]
    if action == "snapshot":
        return nm.snapshot()
    if action == "scan":
        return nm.scan()
    if action == "password":
        current = nm.snapshot()
        if not current["connected"] or current["mode"] != "lan" or current["uuid"] != request["uuid"]:
            raise NetworkError("连接已更改，请刷新。")
        return nm.read_connection_password(current["uuid"])
    if action == "activate":
        config = validate_config(request["config"])
        return nm.activate(config["mode"], config)
    raise ValueError("未知的 Wi-Fi 操作。")

if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.readline(131073))
        result = {"result": dispatch(request, NetworkManager(sys.argv[1]))}
    except (ValueError, KeyError, TypeError, OSError, NetworkError):
        result = {"error": "宿主机 Wi-Fi 操作失败，请检查网卡和网络设置。"}
    print(json.dumps(result))
