# 部署与配置

## Linux 运行方式

需要 Python 3.10+；Debian / Ubuntu 可按需安装 `python3-venv`。首次启动前按 README 创建虚拟环境并安装依赖。

| 命令 | 行为 |
| --- | --- |
| `.venv/bin/python wifi.py --dashboard-only` | 仅系统监测，默认端口 8090，不管理 WiFi。 |
| `.venv/bin/python wifi.py --preview --port 8090` | 读取实际状态并允许可用的扫描，禁止切网、修改热点密码与终止进程。 |
| `sudo bash install.sh` | 安装到 `/opt/helloboard`，默认仅系统看板，尚未启动服务。 |
| `sudo bash install.sh --with-wifi` | 安装并配置 WiFi 管理；随后启动服务才应用网络模式。 |

WiFi 管理需要已启动的 NetworkManager、受管理的无线网卡和 root 权限。Debian 系列可安装 `network-manager dnsmasq-base`；应按设备现有网络方案安排迁移。无线接口自动探测，也可用 `--interface 接口名` 指定。AP 需网卡支持热点。

systemd 服务管理：

```bash
sudo systemctl enable --now helloboard
sudo systemctl status helloboard
sudo journalctl -u helloboard -f
sudo systemctl restart helloboard
sudo systemctl disable --now helloboard
```

服务默认监听所有 IPv4 接口的 80 端口；手动运行可用 `--port` 指定端口。没有 systemd 的 Linux 可直接运行程序，自启交由该系统的服务管理器。WSL / 容器只展示自身环境，不代表宿主机全部指标。

## Windows

使用 `install.ps1` 安装本机虚拟环境，再用 `start.ps1` 启动。可传入 `-Port 8091` 更换端口，`install.ps1 -AutoStart` 注册当前账号的登录任务，不保存账号密码。

若 PowerShell 阻止执行本地脚本，可只对本次进程执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

从局域网访问时，需在 Windows 防火墙为 Python 的专用网络入站访问放行。脚本不修改防火墙。更新前关闭运行窗口或结束 HelloBoard 登录任务，更新代码后重新运行安装与启动命令。Linux 的虚拟环境不能直接复制到 Windows。

## 网络配置

WiFi 管理启用时按程序自身目录定位 `wifi.yaml`，首次创建默认值，不受工作目录影响；安装脚本也会初始化该文件。格式见 [wifi.example.yaml](../wifi.example.yaml)。

- `mode: ap` 创建设备热点，`mode: lan` 连接路由器。
- 默认热点名为 `hellosms`、地址为 `192.168.11.17/24`，默认密码为空。可在网页的设备热点区域设置密码；密码至少八位，保存后在下次启用 AP 或重启时使用。
- 局域网模式使用 DHCP 获取地址，访问时需让浏览器所在设备加入同一网络。新地址可在路由器客户端列表中查找。
- AP 模式使用 NetworkManager shared 模式提供 DHCP / DNS。加入热点后访问 `http://192.168.11.17`（自定义端口时附上端口）。
- 单无线网卡的 AP 与 LAN 通常互斥，切换时网页可能暂时断开。连接失败或持续掉线时，仅在系统具备 AP 能力时恢复热点。
- 成功联网后才保存输入及历史网络；最多保留 100 个历史网络。已保存网络的密码框留空可复用密码。
- 支持开放网络和常见 WPA / WPA2 / WPA3 Personal，不提供企业 802.1X、WEP 或门户网页登录流程。密码支持 8–63 位 ASCII 或 64 位十六进制 PSK。

## 账号验证与进程操作

网页无需整体登录。Linux 通过系统 PAM 验证账号；可用 `--auth-user 用户名` 指定管理账号。默认选择 UID 1000 的账号，非 root 运行时使用当前账号。安装脚本根据发行版已有 PAM 策略生成 HelloBoard 策略；无法识别或缺少依赖时禁用验证功能。

WiFi 敏感操作在同一次服务运行中复用当前浏览器的授权；服务重启后重新验证。系统登录密码不会写入 YAML、浏览器存储或会话。进程终止每次单独验证，最多处理 32 个目标，并核对进程启动标识；关键进程不可选，不支持安全 pidfd 操作时禁止终止。退出请求不保证进程立即结束，服务管理器也可能将它重新启动。

配置中的网络密码以明文保存在设备本地，Linux 使用 `0600` 权限；常规状态接口不返回密码。Web 接口有同源、CSRF 和私有地址访问限制。HTTP 不加密传输，适用于可信局域网，不直接发布公网。

## 更新与历史数据

在源码目录执行 `sudo bash update.sh`。脚本保留 `/opt/helloboard/wifi.yaml`、服务参数与原有自启状态，重启服务，不创建备份。旧版 `/opt/hellosms-wifi` 及对应服务只在首次更新时迁移，后续更新不重复迁移。

系统每两秒采样，历史保留在服务内存中，最长十分钟。刷新网页或切换子页会恢复同一段历史；服务或设备重启会清空历史。进程约每六秒更新，设备与服务等慢变量约十五秒以上更新，不把缺失指标伪造成零。

语言、主题、密度与侧栏偏好保存在当前浏览器，按访问地址独立。清理网站数据后恢复默认：语言为中文、密度为紧凑、主题跟随系统。
