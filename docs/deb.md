# Ubuntu x86_64 离线安装包

适用于使用 systemd 的 Ubuntu 20.04 及更新版本、Intel / AMD 64 位处理器（`uname -m` 为 `x86_64`）。不适用于 ARM64 树莓派、Windows 或 Alpine。目标机器不需要预装 Python、pip 或 Node.js。

## 安装与访问

将 `dist/helloboard_0.1.0-1_amd64.deb` 复制到目标电脑，然后执行：

```bash
sudo dpkg -i ./helloboard_0.1.0-1_amd64.deb
systemctl status helloboard --no-pager
hostname -I
```

安装完成后服务自动启动并设置开机自启，浏览器访问 `http://设备IP/`。默认端口为 80，需要该端口未被其他程序占用；同一网络的手机也可访问。若修改端口，在 `/etc/default/helloboard` 中调整 `--port 80`，然后执行 `sudo systemctl restart helloboard`。防火墙若已启用，需允许所选端口的局域网访问。

Python 3.13.17、Flask、Waitress、PyYAML 及其全部运行依赖、完整字体、静态资源已包含在包中，安装不运行 pip、不下载 Python 包。使用 Ubuntu 自带的 glibc、PAM 和 systemd；精简系统如果缺少这些基础组件，需要先补齐包声明的系统依赖。该包不是整套操作系统镜像。

默认只启动系统看板，不切换目标机器的网络。进程管理和敏感设置继续使用目标机器自己的系统账号验证，不包含当前设备的账号、网络密码或浏览器会话。

## 启用 WiFi 管理

目标电脑需有支持的无线网卡、正在运行的 NetworkManager；AP 功能还需要网卡支持热点，并准备 `dnsmasq-base`。Ubuntu 桌面通常已装 NetworkManager，Ubuntu Server 使用其他网络方案时需先安排网络迁移。

1. 编辑 `/etc/helloboard/wifi.yaml`，填入希望使用的模式和网络信息；AP 密码至少八个字符。
2. 编辑 `/etc/default/helloboard`，删除 `--dashboard-only`。
3. 执行 `sudo systemctl restart helloboard`。之后服务按保存配置管理 WiFi。

启动 WiFi 管理会切换网络，请先准备目标电脑的本地操作方式。默认热点地址是 `192.168.11.17`。

## 目录与维护

| 路径 | 用途 |
| --- | --- |
| `/opt/helloboard` | 应用、静态资源、独立 Python 运行时 |
| `/etc/helloboard/wifi.yaml` | WiFi / AP 配置，仅 root 可读写 |
| `/etc/default/helloboard` | 服务启动参数 |
| `/usr/lib/systemd/system/helloboard.service` | 服务定义 |
| `/usr/share/doc/helloboard` | 使用说明、构建清单和第三方许可证 |

```bash
sudo journalctl -u helloboard -n 80 --no-pager
sudo systemctl restart helloboard
sudo dpkg -i ./新版安装包.deb
sudo apt remove helloboard    # 删除程序，保留配置
sudo apt purge helloboard     # 同时删除包管理的配置文件
```

升级保留配置，并重启已经运行的服务；原本停用的服务不会因升级自动启动。包安装拒绝覆盖源码脚本安装的同名目录或服务，需要先迁移原安装。deb 安装之后应使用 deb 升级，不要混用 `install.sh` / `update.sh`。

## 重新构建

构建机可为 ARM64 或 x86_64 Linux，准备 Python 3.12+、pip、curl、dpkg-deb，使用：

```bash
.venv/bin/python tools/build_deb.py
# 已缓存运行时和 wheel 时，无需网络：
.venv/bin/python tools/build_deb.py --offline
# 如需代理，仅对下载生效，不会记录进安装包：
.venv/bin/python tools/build_deb.py --proxy http://代理IP:端口
```

生成 `.deb`、SHA256 校验文件及大小报告到 `dist/`；下载缓存位于 `~/.cache/helloboard-deb`。构建校验 Python 压缩包及每个 wheel 的 SHA256，仅复制明确列出的应用文件，不打包本机虚拟环境、Git 历史、测试工具或真实 `wifi.yaml`。

运行时来源为 [Astral Python Build Standalone 20261021](https://github.com/astral-sh/python-build-standalone/releases/tag/20261021)，采用基础 x86_64 的 stripped 版本；移除开发头文件、pip 和 Tk 桌面工具，保留应用所需标准库、解释器和动态库。原有六个 HTTP 工作线程、内存优化设置与界面效果均保留。

## 包体与验证

初版包压缩后约 **28.5 MiB**；文件内容约 **90 MiB**，当前 ARM64 / 16KB 页构建环境解包占用约 **125 MiB**。目标文件系统的实际分配大小会有差异，建议预留至少 **150 MiB**，安装过程还需要临时空间。Python 已包含在这些数字内，不需要再复制开发虚拟环境。包内完整中文字体和回退字库均保留。

本次验证包括全部应用单元测试、deb 服务脚本的安装 / 升级 / 卸载行为、配置保留、amd64 ELF 与 glibc 符号需求，以及静态资源逐文件校验。在 ARM64 上通过 QEMU 实际执行包内的 amd64 Python、C 扩展和 Waitress 服务，并验证页面、系统 / 进程接口、gzip 与全部字体响应。尚未在目标 Ubuntu 实机安装；WiFi 硬件、PAM 系统账号验证及开机启动需要目标机器确认。

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python docs/deb_check.py dist/helloboard_0.1.0-1_amd64.deb
# 在 amd64 目标机解包验证时，不会安装或修改网络：
dpkg-deb -x helloboard_0.1.0-1_amd64.deb ./deb-check
python3 docs/deb_runtime_check.py --app ./deb-check/opt/helloboard
```

`deb_runtime_check.py` 强制只读预览并仅监听回环地址；它不接管 WiFi，不终止进程。该检查脚本使用系统 Python 标准库，也支持指定 QEMU 和 x86_64 glibc sysroot 进行跨架构验证。
