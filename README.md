# HelloBoard

轻量、本地部署的系统数据看板，适用于 Raspberry Pi、Ubuntu / Debian 等 Linux 设备，并提供 Windows 只读监测支持。将系统状态与 WiFi 管理整合在统一界面中，兼顾桌面浏览和手机操作。

采用 Flask、原生 HTML / CSS / JavaScript 和 SVG，无前端构建步骤。字体、图标和脚本均由设备本地提供，离线热点环境也可使用。

## 界面预览

**系统状态 · 浅色模式**

![HelloBoard 系统状态浅色界面](docs/images/system-light.png)

**系统状态 · 深色模式**

![HelloBoard 系统状态深色界面](docs/images/system-dark.png)

**WiFi 管理 · 桌面与手机**

<table>
  <tr>
    <td width="74%"><img src="docs/images/wifi-desktop.png" alt="WiFi 管理桌面布局" /></td>
    <td width="26%"><img src="docs/images/wifi-mobile.png" alt="WiFi 管理手机布局" /></td>
  </tr>
</table>

截图使用示例网络与进程数据，不包含设备密码。

## 功能

- **系统监测**：CPU 与各核心占用、内存、存储容量和读写、网卡流量、运行时间，以及设备支持的温度、风扇、供电和服务状态。
- **实时趋势**：每两秒采样，共享最近十分钟历史；刷新或重新打开页面后恢复曲线。
- **进程管理**：名称 / PID 搜索、排序、多选与退出请求；Linux 下验证系统账号，并保护关键进程。
- **WiFi 管理**：扫描、连接、保存历史网络、AP 热点和密码设置；仅在系统与网卡具备相应能力时开放。
- **外观设置**：中英文、深浅色、紧凑 / 宽松布局和可收起侧栏；偏好保存在浏览器本地。

## 布局设计

界面采用“固定导航 + 连续内容面板”的结构，减少重复卡片和装饰，让数据与操作保持清晰。

| 区域 | 设计方式 |
| --- | --- |
| 导航 | 桌面左侧为可收起侧栏，手机改为顶部页签；系统状态与 WiFi 管理使用独立路由。 |
| 系统状态 | 顶部放核心指标，中部为资源与流量趋势，下部展示详细数据。紧凑桌面布局采用四栏，宽松布局采用两栏，小屏自然单栏。 |
| WiFi 管理 | 连接状态、连接配置与附近网络共用一块面板；桌面并排展示，手机按操作顺序纵向排列。 |
| 视觉与交互 | 使用两端渐隐的灰色细线分区，辅以柔和圆角、轻阴影和 SVG 图标；说明与设置收进侧滑面板。 |
| 字体与主题 | 英文及数字使用 Inter，中文使用 Noto Sans SC。深浅色分别定义文字、按钮、表单、状态和图表颜色，避免直接反色。 |

主要点击区域不小于 44px；动画尊重系统“减少动态效果”设置。主题切换不重载页面，布局切换保留输入与选择，不增加数据轮询。

## 平台支持

| 平台 | 系统监测 | WiFi / AP | 进程终止 |
| --- | --- | --- | --- |
| Linux / Raspberry Pi | 支持，按设备能力展示 | 需要 NetworkManager、可用无线网卡与 root 权限；AP 另需网卡支持 | 需要 pidfd、PAM 与相应权限 |
| Windows | 支持，使用 psutil | 暂不支持，自动隐藏入口 | 暂不支持 |

启动时识别平台及能力，缺少的硬件指标自动收起。Windows 已通过模拟环境验证，尚未完成真实 Windows 主机验证。

## 快速开始

需要 **Python 3.10+**。以下命令以 Linux 为例，默认启动系统看板，不切换 WiFi：

```bash
git clone https://gitee.com/gcusms/helloboard.git
cd helloboard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python wifi.py --dashboard-only
```

访问 `http://127.0.0.1:8090`；其他局域网设备使用主机实际 IP。

Windows 在项目目录中运行：

```powershell
.\install.ps1
.\start.ps1
```

如需登录 Windows 后自动启动，可使用 `.\install.ps1 -AutoStart`。更多参数与权限说明见[部署与配置](docs/operations.md)。

### Linux 服务部署

在支持 systemd 的系统中安装并启用看板服务，默认 HTTP 端口为 **80**：

```bash
sudo bash install.sh
sudo systemctl enable --now helloboard
```

需要接管设备 WiFi 时，首次安装改用 `sudo bash install.sh --with-wifi`。首次启用按本地配置切换网络，默认创建名为 `hellosms`、地址为 `192.168.11.17` 的开放热点；建议先设置热点密码，并准备有线连接或本地终端。

更新已安装的服务：

```bash
git pull --ff-only
sudo bash update.sh
```

更新保留 WiFi 配置、服务参数与开机自启状态，不创建备份。**服务会重启，启用 WiFi 管理的设备会重新应用保存的网络模式。**

## 配置与访问

- `/`、`/system_status`：系统状态；`/wifi_config`：WiFi 管理（能力可用时）。
- WiFi 管理首次运行时在程序同目录创建 `wifi.yaml`，保存网络模式、名称、密码和历史记录；示例见 [wifi.example.yaml](wifi.example.yaml)。本机配置不提交到 Git。
- 页面无需整体登录；查看网络密码、修改热点密码和终止进程等操作需验证系统账号。
- 面向可信局域网设计，默认 HTTP，不应直接暴露到公网。网络密码保存在本地配置中，Linux 权限为 `0600`。

## 开发与验证

```bash
.venv/bin/python -m unittest discover -s tests -v
```

后端测试使用临时配置与模拟网卡；进程测试仅操作自行创建的测试进程。浏览器检查脚本位于 `docs/`，需额外安装 Playwright 并准备 `/usr/bin/chromium`；主题检查可运行 `.venv/bin/python docs/theme_check.py`。截图复现脚本为 [docs/capture_readme.py](docs/capture_readme.py)。

主要模块：`wifi.py` 提供 Web 服务，`system_metrics.py` / `portable_metrics.py` 负责数据采集，`controller.py` / `network.py` 管理网络，`process_control.py` 处理进程操作，`templates/` 与 `static/` 提供界面。

## 字体与图标

内置 Inter、Noto Sans SC 字体采用 SIL Open Font License，来源与许可证见 [static/fonts](static/fonts/SOURCES.md)。调色盘图标来自 Lucide，许可证见 [static/lucide-LICENSE.txt](static/lucide-LICENSE.txt)。HelloBoard 品牌图标使用定制 SVG。
