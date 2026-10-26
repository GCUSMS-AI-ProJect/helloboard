"use strict";
// One local dictionary; switching language does not reload or reset form data.
window.HelloBoardI18n = (() => {
  const LANGUAGE_KEY = "helloboard.language";
  let language = "zh";
  try {
    const savedLanguage = localStorage.getItem(LANGUAGE_KEY);
    if (savedLanguage === "zh" || savedLanguage === "en")
      language = savedLanguage;
  } catch {
    // Keep the page usable when browser storage is unavailable.
  }
  const english = {
    "深色模式": "Dark mode",
    "切换为深色模式": "Switch to dark mode",
    "切换为浅色模式": "Switch to light mode",
    "系统": "System",
    信号: "Signal",
    "HelloBoard · 系统状态": "HelloBoard · System status",
    跳到主要内容: "Skip to main content",
    硬件状态: "Hardware status",
    系统状态: "System status",
    内存: "Memory",
    存储: "Storage",
    温度: "Temperature",
    资源趋势: "Resource trends",
    "最近 10 分钟": "Last 10 minutes",
    每秒: "Per second",
    网络流量: "Network traffic",
    接收: "Receive",
    发送: "Send",
    正在采集趋势: "Collecting samples",
    "CPU 和内存趋势": "CPU and memory trends",
    网络接收和发送趋势: "Network receive and send trends",
    处理器与内存: "Processor & memory",
    设备信息: "Device information",
    存储空间: "Storage volumes",
    网络接口: "Network interfaces",
    系统服务: "System services",
    进程: "Processes",
    进程排序: "Sort processes",
    名称: "Name",
    数据更新: "Updates",
    指标说明: "About the metrics",
    只读监测: "Read-only monitoring",
    "设备每两秒持续采样，保留最近十分钟。刷新或重新打开页面会恢复曲线；切到后台只暂停页面更新。服务或设备重启后重新采样。":
      "The device samples every two seconds and retains the last ten minutes. Reloading or reopening restores the curves; background tabs only pause page updates. Sampling starts over when the service or device restarts.",
    "内存占用按总量减可用量计算；进程 CPU 按整机算力计算。设备和服务信息每十五秒更新，进程每六秒更新。缺失或尚未采集的指标显示为横线。":
      "Memory usage is total minus available. Process CPU is a share of total system capacity. Device and service information refreshes every fifteen seconds; processes every six seconds. A dash means unavailable or awaiting a sample.",
    "查看系统状态不会扫描或切换网络。":
      "Viewing system status does not scan or switch networks.",
    搜索进程: "Search processes",
    "搜索名称或 PID": "Search name or PID",
    终止所选进程: "End selected processes",
    选择当前页: "Select this page",
    操作: "Actions",
    清除选择: "Clear selection",
    上一页: "Previous page",
    下一页: "Next page",
    终止进程: "End processes",
    终止方式: "Exit method",
    正常退出: "Normal exit",
    强制终止: "Force quit",
    验证并终止: "Verify & end",
    "正在执行…": "Working…",
    "选择进程 {name}": "Select process {name}",
    选择进程: "Select process",
    "终止进程 {name}": "End process {name}",
    "已选 {selected} · 共 {count} 个": "{selected} selected · {count} total",
    "共 {count} 个": "{count} processes",
    进程列表暂时不可用: "Process list unavailable",
    没有匹配的进程: "No matching processes",
    正在读取进程: "Loading processes",
    进程列表更新中断: "Process updates interrupted",
    "立即强制终止，未保存的数据可能丢失。":
      "Force quit immediately. Unsaved data may be lost.",
    "请求进程正常退出；进程可能需要时间或拒绝退出。":
      "Request a normal exit. The process may take time or ignore the request.",
    "预览模式不允许终止进程。": "Processes cannot be ended in preview mode.",
    "当前系统不支持安全终止进程。":
      "Safe process control is unavailable on this system.",
    受保护的系统进程: "Protected system process",
    进程已退出: "Process has exited",
    已发送退出请求: "Exit requested",
    已发送强制终止信号: "Force quit signal sent",
    "已向 {count} 个进程发送强制终止信号":
      "Force quit signal sent to {count} processes",
    "已向 {count} 个进程发送退出请求": "Exit requested for {count} processes",
    "结果暂时无法确认，请刷新列表后查看。":
      "The result could not be confirmed. Refresh the list to check.",
    "进程已变化，请重新选择。": "The process has changed. Select it again.",
    "没有权限终止此进程。": "Permission to end this process was denied.",
    "暂时无法终止此进程。": "This process could not be ended.",
    "请求格式不正确。": "Invalid request format.",
    "请选择终止方式。": "Select an exit method.",
    "每次请选择 1–32 个进程。": "Select between 1 and 32 processes.",
    "进程标识不正确，请刷新列表。":
      "Invalid process identity. Refresh the list.",
    "请勿重复选择同一个进程。": "Do not select the same process twice.",
    "正在终止进程，请稍后重试。":
      "Processes are being ended. Try again shortly.",
    进程操作: "Process controls",
    "搜索名称或 PID，可跨页选择；每次最多终止 32 个进程，执行时验证系统账号。正常退出发送退出请求，强制终止可能丢失未保存的数据。系统关键进程不可操作。":
      "Search by name or PID and select across pages, up to 32 processes per action. Verify your system account to continue. Normal exit requests shutdown; force quit may lose unsaved data. Critical system processes are protected.",
    刷新状态: "Refresh status",
    刷新中: "Refreshing",
    更新中断: "Updates interrupted",
    暂时无法读取: "Temporarily unavailable",
    实时更新: "Live",
    "{days} 天 {hours} 时 {minutes} 分": "{days}d {hours}h {minutes}m",
    "{count} 核": "{count} cores",
    风扇: "Fan",
    暂无数据: "No data",
    系统负载: "Load (1 / 5 / 15m)",
    可用内存: "Available memory",
    缓存: "Cache",
    缓冲区: "Buffers",
    交换空间: "Swap",
    进程数量: "Process count",
    主机名: "Hostname",
    型号: "Model",
    系统: "OS",
    内核: "Kernel",
    架构: "Architecture",
    运行时间: "Uptime",
    欠压: "Undervoltage",
    频率受限: "Frequency capped",
    降频: "Throttled",
    温度限制: "Thermal limit",
    供电与降频: "Power & throttling",
    正常: "Normal",
    历史限制: "Past limits",
    曾发生: "Recorded",
    无: "None",
    已用: "Used",
    可用: "Available",
    总量: "Total",
    读取速度: "Read rate",
    写入速度: "Write rate",
    累计读取: "Total read",
    累计写入: "Total written",
    在线: "Online",
    离线: "Offline",
    休眠: "Dormant",
    未知: "Unknown",
    有线: "Ethernet",
    地址: "Address",
    累计接收: "Total received",
    累计发送: "Total sent",
    收发错误: "Rx / Tx errors",
    运行中: "Running",
    未运行: "Inactive",
    故障: "Failed",
    启动中: "Starting",
    停止中: "Stopping",
    已启用: "Enabled",
    未启用: "Disabled",
    静态: "Static",
    临时启用: "Runtime enabled",
    开机自启: "Autostart",

    设置密码: "Set password",
    收起侧栏: "Collapse sidebar",
    展开侧栏: "Expand sidebar",
    验证登录: "Verify login",
    验证: "Verify",
    "正在切换…": "Switching…",
    "等待扫描…": "Waiting for scan…",
    预览模式不支持切换网络: "Network switching is unavailable in preview",

    样式设置: "Appearance",
    布局密度: "Layout density",
    宽松: "Relaxed",
    紧凑: "Compact",
    "查看 Wi-Fi 密码": "Show Wi-Fi password",
    "隐藏 Wi-Fi 密码": "Hide Wi-Fi password",
    无密码: "No password",
    本次服务已授权: "Authorized for this service session",
    保存时验证系统账号: "Verify your system account when saving",
    验证系统账号: "Verify system account",
    "当前浏览器验证一次即可，服务重启后需重新验证。":
      "Verify once in this browser. Restarting the service requires verification again.",
    系统用户名: "System username",
    验证并继续: "Verify & continue",
    "请先验证系统用户名和密码。":
      "Please verify your system username and password.",
    "系统用户名或密码不正确。": "Incorrect system username or password.",
    "当前没有连接 Wi-Fi。": "There is no active Wi-Fi connection.",
    "此网络的认证方式不支持显示密码。":
      "Password display is unavailable for this network's authentication method.",
    "当前连接没有可读取的已保存密码。":
      "This connection has no saved password available.",

    "HelloBoard · WiFi 管理": "HelloBoard · WiFi manager",
    "HelloBoard 首页": "HelloBoard home",
    "8–63 位英文字母、数字或符号，也支持 64 位十六进制密钥。保存后，下次开启热点或重启服务时使用.":
      "Use 8–63 ASCII characters or a 64-digit hexadecimal key. Applies the next time the hotspot starts.",
    "8–63 位英文字母、数字或符号，也支持 64 位十六进制密钥。保存后，下次开启热点或重启服务时使用。":
      "Use 8–63 ASCII characters or a 64-digit hexadecimal key. Applies the next time the hotspot starts.",
    "AP 密码": "AP password",
    "Wi-Fi 名称": "Wi-Fi name",
    "Wi-Fi 密码": "Wi-Fi password",
    "。未配置 AP 密码时热点无密码；设置密码后，下次开启热点或重启服务时生效。":
      ". The hotspot is open until you set an AP password. A saved password applies the next time the hotspot or service starts.",
    使用帮助: "Help",
    保存密码: "Save password",
    保存并连接: "Save & connect",
    关闭: "Close",
    关闭侧栏: "Close panel",
    准备切换网络: "Switch network",
    切换为英文: "Switch to English",
    "切换网络后，如何访问？":
      "How do I access the device after switching networks?",
    取消: "Cancel",
    复制地址: "Copy address",
    复制设备地址: "Copy device address",
    "如何连接设备热点？": "How do I use the device hotspot?",
    局域网: "Wi-Fi",
    已保存的网络: "Saved networks",
    开放网络: "Open network",
    当前设备地址: "Current device address",
    "扫描 Wi-Fi": "Scan Wi-Fi",
    "显示 AP 密码": "Show AP password",
    "隐藏 AP 密码": "Hide AP password",
    显示密码: "Show password",
    隐藏密码: "Hide password",
    暂无可用网络: "No networks found",
    系统数据看板: "System dashboard",
    查看连接说明: "Connection help",
    "正在扫描…": "Scanning…",
    正在读取网络: "Reading network status",
    每次保存都需验证: "Required for every save",
    热点名称: "Hotspot name",
    热点密码: "Hotspot password",
    确认切换: "Switch network",
    系统登录密码: "System login password",
    "网络和密码会保存吗？": "Are networks and passwords saved?",
    网络模式: "Network mode",
    "WiFi 管理": "WiFi manager",
    网络设置: "Network settings",
    "至少 8 个字符": "At least 8 characters",
    "设备会恢复热点，原有网络配置保留。连接热点后可重新设置。部分网卡在热点模式只能显示缓存扫描结果，也可以手动输入网络名称。":
      "The device restores its hotspot and keeps your previous settings. Reconnect to the hotspot to try again. Some adapters can only show cached scan results in hotspot mode; you can also enter a network name manually.",
    设备地址: "Device address",
    设备导航: "Device navigation",
    设备热点: "Hotspot",
    "设置 AP 密码": "Set AP password",
    访问地址: "Address",
    读取中: "Loading",
    "跳到 WiFi 管理": "Skip to WiFi manager",
    输入网络密码: "Enter Wi-Fi password",
    "连接 Wi-Fi 后，让手机或电脑也加入同一网络，再使用设备的新 IP 访问。可在路由器的设备列表中查找 IP。":
      "Join the same Wi-Fi on your phone or computer, then open the device’s new IP address. You can find it in your router’s device list.",
    "连接失败怎么办？": "What if a connection fails?",
    "连接成功后，名称和密码自动保存在设备本地 YAML 中。下次打开会自动选中最近使用的网络，也可以从名称输入框右侧选择其他已保存的网络。密码框留空即可复用已保存密码。":
      "After a successful connection, the device saves the network name and password locally. Your latest network is selected next time. Use the name field’s menu to pick another saved network, and leave its password blank to reuse it.",
    连接配置: "Connection",
    "连接页面显示的设备热点，再打开 http://":
      "Join the device hotspot, then open http://",
    选择已保存的网络: "Choose a saved network",
    "选择或输入 Wi-Fi": "Select or enter a Wi-Fi name",
    重新扫描: "Scan again",
    "附近的 WiFi": "Nearby WiFi",
    页面导航: "Page navigation",
    "验证账户：": "Account: ",
    留空使用已保存密码: "Leave blank to use saved password",
    暂无已保存网络: "No saved networks",
    "操作未完成，请重试。":
      "Could not complete the operation. Please try again.",
    "暂时无法连接设备。若刚切换网络，请连接新网络后重新打开设备地址。":
      "Cannot reach the device. If you just switched networks, join the new network and reopen the device address.",
    "正在处理…": "Working…",
    开启设备热点: "Start hotspot",
    设备热点已开启: "Hotspot is on",
    "已连接 Wi-Fi": "Connected to Wi-Fi",
    等待网络连接: "Waiting for a connection",
    切换中: "Switching",
    备用热点: "Recovery hotspot",
    热点模式: "Hotspot",
    未连接: "Disconnected",
    尚未连接无线网络: "No network connected",
    已设置: "Set",
    无密码: "No password",
    "已保存 AP 密码，重新填写可替换。":
      "An AP password is saved. Enter a new one to replace it.",
    "尚未设置密码，默认开放热点。": "No password is set. The hotspot is open.",
    暂不支持此网络的认证方式: "Unsupported network security",
    已连接: "Connected",
    已保存: "Saved",
    加密网络: "Secured network",
    "正在发现附近的网络…": "Scanning nearby networks…",
    未发现网络: "No networks found",
    "Wi-Fi 名称需为 1–32 字节。": "The Wi-Fi name must be 1–32 bytes.",
    "请输入密码，或勾选开放网络。": "Enter a password, or select Open network.",
    "设备地址已复制。": "Device address copied.",
    "请直接复制页面显示的设备地址。":
      "Please copy the device address shown on the page.",
    "{count} 个网络": "{count} networks",
    "信号{quality}，{signal}%": "{quality} signal, {signal}%",
    良好: "Strong",
    一般: "Fair",
    较弱: "Weak",
    "将开启 {ssid}。请连接该热点后访问 http://{address}。当前网络会断开。":
      "Start {ssid}? Your current connection will disconnect. Join the hotspot, then open http://{address}.",
    "将连接 {ssid}。请让手机或电脑也连接该网络，再通过设备的新 IP 打开本页；可在路由器设备列表中查找。若连接失败，请重新连接 {ap} 热点。":
      "Connect to {ssid}? Join the same network on your phone or computer, then open the device’s new IP from your router’s device list. If the connection fails, reconnect to {ap}.",
    "正在切换网络，网页可能暂时断开。连接失败时，请连接 {ssid} 并访问 http://{address}。":
      "Switching networks. This page may disconnect briefly. If the connection fails, join {ssid} and open http://{address}.",
    "已保存，下次开启热点或重启服务时生效。":
      "Saved. Applies next time the hotspot or service starts.",
    "请输入系统登录密码。": "Enter the system login password.",
    "正在验证密码，请稍后再试。":
      "A password check is in progress. Please try again shortly.",
    "请稍后重试系统密码验证。":
      "Please wait a moment before trying the system password again.",
    "系统密码验证不可用，请检查 PAM 配置。":
      "System authentication is unavailable. Check the device’s PAM configuration.",
    "系统登录密码不正确或账户不可用。":
      "Incorrect system password or the account is unavailable.",
    "预览模式：可查看状态和扫描，网络切换尚未启用。":
      "Preview: status and scanning are available. Network changes are disabled.",
    "预览模式不允许修改配置。": "Settings cannot be changed in preview mode.",
    "正在准备网络。": "Preparing the network.",
    "正在处理网络操作，请稍后再试。":
      "A network operation is in progress. Please try again shortly.",
    "正在连接 Wi-Fi。": "Connecting to Wi-Fi.",
    "正在开启热点。": "Starting the hotspot.",
    "Wi-Fi 已连接。": "Connected to Wi-Fi.",
    "热点已开启。": "Hotspot is on.",
    "即将切换网络。当前网页可能暂时断开，请连接新网络后重新打开。":
      "Switching networks. Join the new network and reopen this page if it disconnects.",
    "配置格式不正确。": "Invalid settings.",
    "AP 密码至少需要 8 个字符。":
      "The AP password must contain at least 8 characters.",
    "密码需为 8–63 位 ASCII 字符，或 64 位十六进制密钥。":
      "Use 8–63 ASCII characters or a 64-digit hexadecimal key.",
    "名称和密码不能包含换行或控制字符。":
      "Names and passwords cannot contain line breaks or control characters.",
    "网卡当前无法主动扫描，显示最近的扫描结果。也可以手动输入名称。":
      "Live scanning is unavailable. Showing cached results; you can also enter a name manually.",
    "NetworkManager 操作失败，请检查网卡、权限或 Wi-Fi 密码。":
      "NetworkManager could not complete the operation. Check the adapter, permissions and Wi-Fi password.",
    "连接或保存失败。 已开启配置热点，原有配置已保留。":
      "Connection or saving failed. The recovery hotspot is on and previous settings are preserved.",
    "尚未设置 Wi-Fi。 已开启配置热点，原有配置已保留。":
      "No Wi-Fi is configured. The recovery hotspot is on and previous settings are preserved.",
    "无线连接已中断。 已开启配置热点，原有配置已保留。":
      "The wireless connection was lost. The recovery hotspot is on and previous settings are preserved.",
    "热点恢复失败，稍后会重试。请检查无线网卡和 NetworkManager。":
      "Could not restore the hotspot. Retrying soon. Check the adapter and NetworkManager.",
    "热点启动失败，稍后会重试。": "Could not start the hotspot. Retrying soon.",
    "页面已过期，请刷新后重试。":
      "This page has expired. Refresh and try again.",
    "请求来源不匹配，请刷新页面。":
      "Request origin mismatch. Refresh and try again.",
    "请求格式必须是 JSON。": "The request must be JSON.",
    "操作未完成，请稍后重试。":
      "Could not complete the operation. Please try again shortly.",
    "请选择热点或局域网模式。": "Select hotspot or Wi-Fi mode.",
    "Wi-Fi 名称需为 1–32 字节，中文通常每字占 3 字节。":
      "The Wi-Fi name must be 1–32 bytes.",
    "网络命令不可用或执行超时，请检查 NetworkManager。":
      "The network command is unavailable or timed out. Check NetworkManager.",
    "这块无线网卡不支持 AP 热点模式。":
      "This wireless adapter does not support hotspot mode.",
    "连接未能取得预期的 IP 地址。":
      "The connection did not obtain the expected IP address.",
    "Wi-Fi 名称和密码必须是文字。": "The Wi-Fi name and password must be text.",
    "Wi-Fi 配置格式不正确。": "Invalid Wi-Fi settings.",
    "wifi.yaml 格式有误，请检查缩进和引号。":
      "Invalid wifi.yaml. Check indentation and quotation marks.",
    "尚未设置 Wi-Fi。": "No Wi-Fi is configured.",
    "已保存的网络列表格式不正确，最多保存 100 个网络。":
      "Invalid saved network list. Up to 100 networks can be saved.",
    "已开始切换，请稍候。": "Switching networks. Please wait.",
    "当前是预览模式，尚未启用网络切换服务。":
      "Network changes are disabled in preview mode.",
    "无线网卡名称不正确。": "Invalid wireless adapter name.",
    "无线连接已中断。": "The wireless connection was lost.",
    "模式必须为 ap 或 lan。": "The mode must be ap or lan.",
    "热点地址必须是有效的 IPv4 地址。":
      "The hotspot address must be a valid IPv4 address.",
    "热点地址需使用私有地址，且不能是 /24 网段的网络或广播地址。":
      "Use a private hotspot IP that is not a /24 network or broadcast address.",
    "请求无效。": "Invalid request.",
    "请通过设备的局域网或热点 IP 地址访问。":
      "Open the device’s local network or hotspot IP address.",
    "连接或保存失败。": "Connection or saving failed.",
    "连接或保存失败。 正在恢复热点。":
      "Connection or saving failed. Restoring the hotspot.",
    "尚未设置 Wi-Fi。 正在恢复热点。":
      "No Wi-Fi is configured. Starting the hotspot.",
    "无线连接已中断。 正在恢复热点。":
      "The wireless connection was lost. Restoring the hotspot.",
  };
  Object.assign(english, {
  "运行环境": "Runtime environment",
  "手动": "Manual",
  "当前仅运行系统看板。": "Only the system dashboard is enabled.",
  "当前系统暂不支持 WiFi 配置与热点管理。": "WiFi configuration and hotspot management are not supported on this system yet.",
  "未安装 NetworkManager，仅显示系统状态。": "NetworkManager is not installed. System monitoring is available.",
  "NetworkManager 未运行，仅显示系统状态。": "NetworkManager is not running. System monitoring is available.",
  "没有可用的无线网卡，仅显示系统状态。": "No available wireless adapter. System monitoring is available.",
  "当前权限仅支持查看和扫描 WiFi。": "Current permissions allow WiFi viewing and scanning only.",
  "当前系统未启用账号验证，仅支持查看。": "System account authentication is unavailable. Read-only access is enabled.",
  "当前系统仅支持查看进程。": "Process monitoring only is available on this system.",
  "当前无线网卡不支持 AP 热点，连接失败后请通过原有网络访问。": "This adapter does not support hotspots. Use the existing network if a connection fails.",
  "当前无线网卡不支持 AP 热点。连接失败后，请通过设备的其他网络地址访问。": "This adapter does not support hotspots. If connection fails, use another device network address."
});
  function t(message, values = {}) {
    let text = language === "en" ? english[message] || message : message;
    return text.replace(/\{(\w+)\}/g, (match, key) => values[key] ?? match);
  }
  function applyStatic() {
    document.documentElement.lang = language === "en" ? "en" : "zh-CN";
    for (const element of document.querySelectorAll("[data-i18n]"))
      element.textContent = t(element.dataset.i18n);
    for (const attr of ["aria-label", "title", "placeholder"]) {
      for (const element of document.querySelectorAll(`[data-i18n-${attr}]`))
        element.setAttribute(
          attr,
          t(element.getAttribute(`data-i18n-${attr}`)),
        );
    }
    const label = language === "zh" ? "切换为英文" : "Switch to Chinese";
    document
      .querySelector("#language-toggle")
      .setAttribute("aria-label", label);
    document.querySelector("#language-toggle").title = label;
    document.querySelector("#language-label").textContent =
      language === "zh" ? "EN" : "中文";
  }
  function toggle() {
    language = language === "zh" ? "en" : "zh";
    try {
      localStorage.setItem(LANGUAGE_KEY, language);
    } catch {
      // Switching still works for this page if preferences cannot be saved.
    }
    applyStatic();
    window.dispatchEvent(new Event("helloboard:language"));
  }
  return {
    t,
    applyStatic,
    toggle,
    get language() {
      return language;
    },
  };
})();
