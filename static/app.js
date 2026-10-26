"use strict";
const { t } = window.HelloBoardI18n;
const $ = (selector) => document.querySelector(selector);
let csrf = $('meta[name="csrf-token"]').content;
let mode = "lan";
let status = null;
let initialized = false;
let networks = [];
let selectedSsid = "";
let timer;
let toastHideTimer;
let toastFrame;
let scanning = false;
let scanTask = null;
let confirmingSwitch = false;
let postingSwitch = false;
let switching = false;
let pending = null;
let savedNetworks = [];
let savingAp = false;
let authorized = false;
let authorizationRequest = null;
let revealedSsid = null;
let revealing = false;
let revealedOpenNetwork = false;
let revealedApPassword = null;
let revealingAp = false;
let activePanel = "help";
const panelTitles = { ap: "AP 密码", help: "使用帮助", style: "样式设置" };
window.HelloBoardCanCloseDialog = (dialog) =>
  !(dialog.id === "authorize-dialog" && $("#authorize-submit").disabled) &&
  !(dialog.id === "confirm-dialog" && postingSwitch);
function networkChanging() {
  return (
    switching ||
    Boolean(
      status?.busy &&
      ["queued", "connecting", "recovering"].includes(status.phase),
    )
  );
}
function clearConnectionPassword() {
  revealedSsid = null;
  revealedOpenNetwork = false;
  $("#connection-secret").textContent = "••••••••";
  renderPasswordControl();
}
function renderPasswordControl() {
  if (revealedSsid !== null && revealedOpenNetwork)
    $("#connection-secret").textContent = t("无密码");
  $("#connection-password-area").hidden =
    !status?.connected || status.mode !== "lan";
  $("#reveal-password").setAttribute(
    "aria-pressed",
    String(revealedSsid !== null),
  );
  const label = t(
    revealedSsid !== null ? "隐藏 Wi-Fi 密码" : "查看 Wi-Fi 密码",
  );
  $("#reveal-password").setAttribute("aria-label", label);
  $("#reveal-password").title = label;
  $("#reveal-password").disabled = revealing || Boolean(status?.busy);
  $("#ap-auth-state").textContent = t(
    authorized ? "本次服务已授权" : "保存时验证系统账号",
  );
}
function renderApPasswordControl() {
  $("#ap-security").textContent =
    revealedApPassword === null
      ? status?.ap_has_password
        ? t("已设置")
        : t("无密码")
      : revealedApPassword || t("无密码");
  const button = $("#reveal-ap-password");
  const label = t(
    revealedApPassword === null ? "显示 AP 密码" : "隐藏 AP 密码",
  );
  button.setAttribute("aria-label", label);
  button.title = label;
  button.setAttribute("aria-pressed", String(revealedApPassword !== null));
  button.disabled = !status || revealingAp;
}
function clearApPassword() {
  revealedApPassword = null;
  renderApPasswordControl();
}
function setAuthorized(value) {
  authorized = Boolean(value);
  if (!authorized) {
    clearConnectionPassword();
    clearApPassword();
  }
  renderPasswordControl();
}
function ensureAuthorization() {
  if (authorized) return Promise.resolve();
  if (authorizationRequest) return authorizationRequest.promise;
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  authorizationRequest = { promise, resolve, reject };
  $("#auth-password").value = "";
  $("#auth-error").hidden = true;
  showDialog($("#authorize-dialog"));
  $("#auth-password").focus();
  return promise;
}
async function authorizedApi(path, payload) {
  await ensureAuthorization();
  try {
    return await api(path, payload);
  } catch (error) {
    if (!error.authorizationRequired) throw error;
    setAuthorized(false);
    await ensureAuthorization();
    return await api(path, payload);
  }
}
let lastScanMessage = "正在扫描…";
function scanMessage(message) {
  lastScanMessage = message;
  $("#scan-message").textContent = t(message);
}

function isOpen(network) {
  return (
    network.security === "--" || network.security === "\u5f00\u653e\u7f51\u7edc"
  );
}
function savedNetwork(ssid = $("#ssid").value) {
  return savedNetworks.find((network) => network.ssid === ssid);
}
function passwordHint() {
  $("#password").placeholder = savedNetwork()?.has_password
    ? t("留空使用已保存密码")
    : t("输入网络密码");
}
function savedMenu(open) {
  $("#saved-network-menu").hidden = !open;
  for (const selector of ["#ssid", "#saved-network-toggle"])
    $(selector).setAttribute("aria-expanded", String(open));
  if (!open) $("#ssid").removeAttribute("aria-activedescendant");
}
function chooseSaved(network) {
  selectedSsid = network.ssid;
  $("#ssid").value = network.ssid;
  $("#password").value = "";
  $("#open-network").checked = !network.has_password;
  $("#password").disabled = !network.has_password;
  passwordHint();
  savedMenu(false);
  renderNetworks();
  $("#ssid").focus();
}
function renderSavedNetworks() {
  const menu = $("#saved-network-menu");
  menu.replaceChildren();
  savedNetworks.forEach((network, index) => {
    const item = document.createElement("li");
    item.id = "saved-network-" + index;
    item.setAttribute("role", "option");
    item.setAttribute(
      "aria-selected",
      String(network.ssid === $("#ssid").value),
    );
    item.textContent = network.ssid;
    item.addEventListener("click", () => chooseSaved(network));
    menu.append(item);
  });
  if (!savedNetworks.length) {
    const item = document.createElement("li");
    item.className = "saved-empty";
    item.setAttribute("role", "option");
    item.setAttribute("aria-disabled", "true");
    item.textContent = t("暂无已保存网络");
    menu.append(item);
  }
}
function signalIcon(signal) {
  const level = signal >= 65 ? 3 : signal >= 35 ? 2 : 1;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    t("信号{quality}，{signal}%", {
      quality: level === 3 ? t("良好") : level === 2 ? t("一般") : t("较弱"),
      signal,
    }),
  );
  svg.classList.add("signal-icon");
  svg.dataset.level = level;
  [
    "M2 7.7Q12-.5 22 7.7L19.8 10Q12 3.5 4.2 10Z",
    "M5.2 11.2Q12 5.5 18.8 11.2L16.5 13.5Q12 9.8 7.5 13.5Z",
    "M8.5 15Q12 12.1 15.5 15L12 19Z",
  ].forEach((d, index) => {
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", d);
    path.setAttribute("opacity", level >= 3 - index ? "1" : ".18");
    svg.append(path);
  });
  return svg;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}
function toast(message, { duration = 4000 } = {}) {
  const element = $("#toast");
  clearTimeout(timer);
  clearTimeout(toastHideTimer);
  cancelAnimationFrame(toastFrame);
  element.textContent = t(message);
  element.hidden = false;
  // Paint the transparent state first; no forced layout or animation loop.
  toastFrame = requestAnimationFrame(() => {
    toastFrame = requestAnimationFrame(() => element.classList.add("visible"));
  });
  timer = setTimeout(() => {
    cancelAnimationFrame(toastFrame);
    element.classList.remove("visible");
    toastHideTimer = setTimeout(
      () => {
        element.hidden = true;
      },
      matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 120,
    );
  }, duration);
}
function notice(message) {
  $("#notice").textContent = t(message);
  $("#notice").hidden = !message;
}
async function api(path, payload, retryCsrf = true) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 22000);
  try {
    const response = await fetch("/api/" + path, {
      method: payload === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      // A service restart rotates the session key. Re-sync once before asking
      // for authorization; the rejected request has not performed any action.
      if (data.csrf_expired && retryCsrf && payload !== undefined) {
        const fresh = await api("status");
        csrf = fresh.csrf_token;
        setAuthorized(fresh.authorized);
        return await api(path, payload, false);
      }
      const error = new Error(t(data.error) || t("操作未完成，请重试。"));
      error.authorizationRequired = Boolean(data.authorization_required);
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError" || error instanceof TypeError) {
      throw new Error(
        t("暂时无法连接设备。若刚切换网络，请连接新网络后重新打开设备地址。"),
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
function controls() {
  $("#mode-ap").disabled = status?.capabilities?.ap === false;
  $("#mode-ap").title = status?.capabilities?.ap === false ? t("这块无线网卡不支持 AP 热点模式。") : "";
  $("#scan-button").disabled = scanning || switching || Boolean(status?.busy);
  const changing = networkChanging();
  $("#connect-button").disabled =
    !status || changing || confirmingSwitch || Boolean(status?.preview);
  $("#connect-button span").textContent = changing
    ? t("正在切换…")
    : mode === "ap"
      ? t("开启设备热点")
      : t("保存并连接");
  $("#connect-button").title = t(
    !status
      ? "正在读取网络"
      : status.preview
        ? "预览模式不支持切换网络"
        : changing
          ? "正在切换…"
          : mode === "ap"
            ? "开启设备热点"
            : "保存并连接",
  );
  $("#save-ap-password").disabled =
    !status ||
    savingAp ||
    switching ||
    Boolean(status?.busy) ||
    Boolean(status?.preview) || status?.capabilities?.ap === false;
}
function setMode(value) {
  if (value === "ap" && status?.capabilities?.ap === false) return;
  mode = value;
  if (value !== "ap") clearApPassword();
  $(".mode-switch").dataset.mode = value;
  for (const name of ["lan", "ap"]) {
    $("#mode-" + name).classList.toggle("selected", name === mode);
    $("#mode-" + name).setAttribute("aria-pressed", String(name === mode));
    $("#" + name + "-fields").hidden = name !== mode;
  }
  $("#ssid").required = mode === "lan";
  controls();
}
function renderStatus() {
  if (!status) return;
  const changing =
    status.busy &&
    ["queued", "connecting", "recovering"].includes(status.phase);
  $("#status-title").textContent = status.connected
    ? status.mode === "ap"
      ? t("设备热点已开启")
      : t("已连接 Wi-Fi")
    : t("等待网络连接");
  $("#status-badge").textContent = changing
    ? t("切换中")
    : status.fallback
      ? t("备用热点")
      : status.mode === "ap"
        ? t("热点模式")
        : status.connected
          ? t("局域网")
          : t("未连接");
  $("#status-badge").dataset.state =
    changing || status.fallback
      ? "pending"
      : status.phase === "error"
        ? "error"
        : status.connected
          ? "connected"
          : "idle";
  $("#connection-name").textContent = status.ssid || t("尚未连接无线网络");
  if (
    !status.connected ||
    status.mode !== "lan" ||
    (revealedSsid !== null && revealedSsid !== status.ssid)
  )
    clearConnectionPassword();
  renderPasswordControl();
  $("#ap-name").textContent = status.ap_ssid;
  $("#ap-address").textContent = status.ap_address;
  $("#help-ap-address").textContent = status.ap_address;
  renderApPasswordControl();
  $("#ap-password-state").textContent = status.ap_has_password
    ? t("已保存 AP 密码，重新填写可替换。")
    : t("尚未设置密码，默认开放热点。");
  $("#device-address").textContent = status.address || "—";
  if (status.address)
    $("#device-address").href =
      "http://" + status.address + (location.port ? ":" + location.port : "");
  else $("#device-address").removeAttribute("href");
  $("#copy-address").disabled = !status.address;
}
async function refreshStatus() {
  try {
    const previousConnection = `${status?.connected}:${status?.mode}:${status?.ssid}`;
    status = await api("status");
    if (status.capabilities?.ap === false && mode === "ap") setMode("lan");
    if (status.csrf_token) csrf = status.csrf_token;
    setAuthorized(status.authorized);
    const nextSaved = status.saved_networks || [];
    const savedChanged =
      JSON.stringify(nextSaved) !== JSON.stringify(savedNetworks);
    if (savedChanged) {
      savedNetworks = nextSaved;
      renderSavedNetworks();
    }
    if (!initialized) {
      $("#ssid").value = status.saved_ssid;
      selectedSsid = status.saved_ssid;
      initialized = true;
      $("#open-network").checked = Boolean(
        savedNetwork() && !savedNetwork().has_password,
      );
      $("#password").disabled = $("#open-network").checked;
      renderSavedNetworks();
    }
    passwordHint();
    renderStatus();
    if (
      savedChanged ||
      previousConnection !== `${status.connected}:${status.mode}:${status.ssid}`
    )
      renderNetworks();
    if (
      status.preview ||
      status.fallback ||
      status.phase === "error" ||
      status.busy
    )
      notice(status.message);
    else if (!switching) notice("");
    if (
      switching &&
      !status.busy &&
      !["queued", "connecting", "recovering"].includes(status.phase)
    ) {
      switching = false;
      notice(status.message);
      $("#password").value = "";
    }
    controls();
  } catch (error) {
    notice(error.message);
  }
}
function renderNetworks() {
  $("#network-list").replaceChildren();
  $("#scan-empty").hidden = networks.length > 0;
  for (const network of networks) {
    network.active = Boolean(
      status?.connected &&
      status.mode === "lan" &&
      status.ssid === network.ssid,
    );
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "network-row";
    button.classList.toggle("chosen", network.ssid === selectedSsid);
    button.setAttribute("aria-pressed", String(network.ssid === selectedSsid));
    button.disabled = !network.supported;
    const symbol = document.createElement("span");
    symbol.className = "network-icon";
    symbol.append(signalIcon(network.signal));
    const copy = document.createElement("span");
    copy.className = "network-copy";
    const title = document.createElement("strong");
    title.textContent = network.ssid;
    const detail = document.createElement("span");
    detail.textContent = !network.supported
      ? t("暂不支持此网络的认证方式")
      : network.active
        ? t("已连接")
        : savedNetwork(network.ssid)
          ? t("已保存")
          : isOpen(network)
            ? t("开放网络")
            : t("加密网络");
    copy.append(title, detail);
    button.append(symbol, copy);
    button.append(
      icon(
        network.active || network.ssid === selectedSsid
          ? "check"
          : isOpen(network)
            ? "wifi"
            : "lock",
      ),
    );
    button.addEventListener("click", () => {
      selectedSsid = network.ssid;
      $("#ssid").value = network.ssid;
      $("#password").value = "";
      $("#open-network").checked = isOpen(network);
      $("#password").disabled = $("#open-network").checked;
      passwordHint();
      savedMenu(false);
      setMode("lan");
      renderNetworks();
      if (!$("#open-network").checked) $("#password").focus();
    });
    item.append(button);
    $("#network-list").append(item);
  }
}
function scan() {
  if (!scanTask)
    scanTask = runScan().finally(() => {
      scanTask = null;
    });
  return scanTask;
}
async function runScan() {
  scanning = true;
  controls();
  $("#scan-button").classList.add("spinning");
  scanMessage(t("正在发现附近的网络…"));
  try {
    const data = await api("scan", {});
    networks = data.networks;
    renderNetworks();
    scanMessage(
      data.warning ||
        (networks.length
          ? t("{count} 个网络", { count: networks.length })
          : t("未发现网络")),
    );
  } catch (error) {
    scanMessage(error.message);
  } finally {
    scanning = false;
    $("#scan-button").classList.remove("spinning");
    await refreshStatus();
    controls();
  }
}
$("#mode-lan").addEventListener("click", () => setMode("lan"));
$("#mode-ap").addEventListener("click", () => setMode("ap"));
$("#scan-button").addEventListener("click", scan);
$("#show-password").addEventListener("click", () => {
  const show = $("#password").type === "password";
  $("#password").type = show ? "text" : "password";
  $("#show-password").setAttribute("aria-pressed", String(show));
  $("#show-password").setAttribute(
    "aria-label",
    show ? t("隐藏密码") : t("显示密码"),
  );
});
$("#open-network").addEventListener("change", () => {
  $("#password").disabled = $("#open-network").checked;
});
$("#ssid").addEventListener("input", () => {
  selectedSsid = $("#ssid").value;
  passwordHint();
  renderSavedNetworks();
  renderNetworks();
});
$("#connect-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!status || status.preview || networkChanging() || confirmingSwitch)
    return;
  pending = { mode };
  if (mode === "lan") {
    const ssid = $("#ssid").value;
    if (!ssid || new TextEncoder().encode(ssid).length > 32)
      return toast(t("Wi-Fi 名称需为 1–32 字节。"));
    let password = $("#password").value;
    if ($("#open-network").checked) password = "";
    else if (!password && savedNetwork(ssid)?.has_password) password = null;
    else if (!password) return toast(t("请输入密码，或勾选开放网络。"));
    Object.assign(pending, { ssid, password });
  }
  $("#confirm-message").textContent =
    mode === "ap"
      ? t(
          "将开启 {ssid}。请连接该热点后访问 http://{address}。当前网络会断开。",
          { ssid: status.ap_ssid, address: status.ap_address },
        )
      : t(
          "将连接 {ssid}。请让手机或电脑也连接该网络，再通过设备的新 IP 打开本页；可在路由器设备列表中查找。若连接失败，请重新连接 {ap} 热点。",
          { ssid: pending.ssid, ap: status.ap_ssid },
        );
  if (mode === "lan" && status.capabilities?.ap === false)
    $("#confirm-message").textContent = t("当前无线网卡不支持 AP 热点。连接失败后，请通过设备的其他网络地址访问。");
  showDialog($("#confirm-dialog"));
});
for (const id of ["confirm-close", "cancel-switch"])
  $("#" + id).addEventListener("click", () => {
    if (!postingSwitch) closeDialog($("#confirm-dialog"));
  });
$("#confirm-dialog").addEventListener("close", () => {
  if (!postingSwitch) {
    pending = null;
    confirmingSwitch = false;
    $("#confirm-switch").disabled = false;
    $("#confirm-switch").textContent = t("确认切换");
    controls();
  }
});
$("#confirm-switch").addEventListener("click", async () => {
  if (confirmingSwitch || !pending) return;
  const request = pending;
  confirmingSwitch = true;
  $("#confirm-switch").disabled = true;
  controls();
  try {
    if (scanTask) {
      $("#confirm-switch").textContent = t("等待扫描…");
      await scanTask;
    }
    if (
      pending !== request ||
      !$("#confirm-dialog").open ||
      $("#confirm-dialog").classList.contains("closing")
    )
      return;
    postingSwitch = true;
    $("#confirm-switch").textContent = t("正在切换…");
    $("#confirm-close").disabled = true;
    $("#cancel-switch").disabled = true;
    await api("connect", request);
    switching = true;
    await closeDialog($("#confirm-dialog"));
    notice(
      status.capabilities?.ap === false ? t("当前无线网卡不支持 AP 热点。连接失败后，请通过设备的其他网络地址访问。") : t(
        "正在切换网络，网页可能暂时断开。连接失败时，请连接 {ssid} 并访问 http://{address}。",
        { ssid: status.ap_ssid, address: status.ap_address },
      ),
    );
  } catch (error) {
    await closeDialog($("#confirm-dialog"));
    toast(error.message);
  } finally {
    if (pending === request || pending === null) {
      pending = null;
      confirmingSwitch = false;
      postingSwitch = false;
      $("#confirm-switch").disabled = false;
      $("#confirm-switch").textContent = t("确认切换");
      $("#confirm-close").disabled = false;
      $("#cancel-switch").disabled = false;
      controls();
    }
  }
});
$("#copy-address").addEventListener("click", async () => {
  const text = $("#device-address").href;
  try {
    if (navigator.clipboard && window.isSecureContext)
      await navigator.clipboard.writeText(text);
    else {
      const field = document.createElement("textarea");
      field.value = text;
      document.body.append(field);
      field.select();
      const copied = document.execCommand("copy");
      field.remove();
      if (!copied) throw new Error();
    }
    toast("设备地址已复制。", { duration: 1600 });
  } catch {
    toast(t("请直接复制页面显示的设备地址。"));
  }
});
async function poll() {
  await refreshStatus();
  setTimeout(poll, 5000);
}
controls();
poll();
scan();

// Saved networks use one small native DOM listbox; no menu framework is needed.
$("#saved-network-toggle").addEventListener("click", () => {
  renderSavedNetworks();
  savedMenu($("#saved-network-menu").hidden);
  $("#ssid").focus();
});
$("#ssid").addEventListener("keydown", (event) => {
  const menu = $("#saved-network-menu");
  if (event.key === "Escape") {
    savedMenu(false);
    event.preventDefault();
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) return;
  const options = [
    ...menu.querySelectorAll('[role="option"]:not([aria-disabled])'),
  ];
  if (event.key === "Enter") {
    if (!menu.hidden) {
      event.preventDefault();
      const selected = options.find(
        (item) => item.id === $("#ssid").getAttribute("aria-activedescendant"),
      );
      if (selected) chooseSaved(savedNetworks[options.indexOf(selected)]);
    }
    return;
  }
  event.preventDefault();
  savedMenu(true);
  if (!options.length) return;
  const current = options.findIndex(
    (item) => item.id === $("#ssid").getAttribute("aria-activedescendant"),
  );
  const next =
    current < 0
      ? event.key === "ArrowUp"
        ? options.length - 1
        : 0
      : (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) %
        options.length;
  options.forEach((item, index) =>
    item.classList.toggle("highlighted", index === next),
  );
  $("#ssid").setAttribute("aria-activedescendant", options[next].id);
  options[next].scrollIntoView({ block: "nearest" });
});
$("#ssid").addEventListener("blur", () => {
  // Allow a pointer click on an option to finish before closing.
  setTimeout(() => {
    if (!document.activeElement?.closest(".ssid-field")) savedMenu(false);
  }, 120);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".ssid-field")) savedMenu(false);
});

const panel = $("#side-panel");
function closePanel() {
  return closeDialog(panel);
}
for (const button of document.querySelectorAll("[data-panel]")) {
  button.addEventListener("click", () => {
    activePanel = button.dataset.panel;
    $("#panel-title").textContent = t(panelTitles[activePanel]);
    for (const name of ["help", "ap", "style"])
      $("#" + name + "-content").hidden = name !== activePanel;
    $("#ap-password-error").hidden = true;
    savedMenu(false);
    showDialog(panel);
    document.body.classList.add("panel-open");
  });
}
$("#panel-close").addEventListener("click", closePanel);
panel.addEventListener("close", () => {
  document.body.classList.remove("panel-open");
  $("#ap-password").value = "";
  $("#ap-password").type = "password";
  $("#show-ap-password").setAttribute("aria-pressed", "false");
  $("#show-ap-password").setAttribute("aria-label", t("显示 AP 密码"));
});
$("#show-ap-password").addEventListener("click", () => {
  const show = $("#ap-password").type === "password";
  $("#ap-password").type = show ? "text" : "password";
  $("#show-ap-password").setAttribute("aria-pressed", String(show));
  $("#show-ap-password").setAttribute(
    "aria-label",
    show ? t("隐藏 AP 密码") : t("显示 AP 密码"),
  );
});
$("#ap-password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (savingAp || !status || status.preview || status.busy || switching) return;
  savingAp = true;
  controls();
  $("#ap-password-error").hidden = true;
  try {
    const result = await authorizedApi("ap-password", {
      password: $("#ap-password").value,
    });
    $("#ap-password").value = "";
    clearApPassword();
    await refreshStatus();
    closePanel();
    toast(result.message);
  } catch (error) {
    if (!error.cancelled) {
      $("#ap-password-error").textContent = t(error.message);
      $("#ap-password-error").hidden = false;
    }
  } finally {
    savingAp = false;
    controls();
  }
});

// Only the signed browser session records a grant; system credentials are never retained.
const authDialog = $("#authorize-dialog");
function cancelAuthorization() {
  if (!$("#authorize-submit").disabled) closeDialog(authDialog);
}
$("#authorize-close").addEventListener("click", cancelAuthorization);
$("#authorize-cancel").addEventListener("click", cancelAuthorization);
authDialog.addEventListener("close", () => {
  $("#auth-password").value = "";
  if (authorizationRequest) {
    const error = new Error();
    error.cancelled = true;
    authorizationRequest.reject(error);
    authorizationRequest = null;
  }
});
$("#authorize-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if ($("#authorize-submit").disabled) return;
  $("#authorize-submit").disabled = true;
  $("#auth-error").hidden = true;
  const credentials = {
    username: $("#auth-username").value,
    password: $("#auth-password").value,
  };
  $("#auth-password").value = "";
  try {
    await api("authorize", credentials);
    setAuthorized(true);
    const request = authorizationRequest;
    authorizationRequest = null;
    await closeDialog(authDialog);
    request?.resolve();
  } catch (error) {
    $("#auth-error").textContent = error.message;
    $("#auth-error").hidden = false;
    $("#auth-password").focus();
  } finally {
    credentials.password = "";
    $("#authorize-submit").disabled = false;
  }
});
$("#reveal-password").addEventListener("click", async () => {
  if (revealedSsid !== null) {
    clearConnectionPassword();
    return;
  }
  if (revealing) return;
  revealing = true;
  renderPasswordControl();
  try {
    const result = await authorizedApi("connection-password", {});
    if (
      status?.connected &&
      status.mode === "lan" &&
      result.ssid === status.ssid
    ) {
      revealedSsid = result.ssid;
      revealedOpenNetwork = !result.password;
      $("#connection-secret").textContent = result.password || t("无密码");
    }
  } catch (error) {
    if (!error.cancelled) toast(error.message);
  } finally {
    revealing = false;
    renderPasswordControl();
  }
});

$("#reveal-ap-password").addEventListener("click", async () => {
  if (revealedApPassword !== null) {
    clearApPassword();
    return;
  }
  if (revealingAp) return;
  revealingAp = true;
  renderApPasswordControl();
  try {
    const result = await authorizedApi("ap-password/reveal", {});
    if (mode === "ap" && authorized) revealedApPassword = result.password;
  } catch (error) {
    if (!error.cancelled) toast(error.message);
  } finally {
    revealingAp = false;
    renderApPasswordControl();
  }
});

$("#language-toggle").addEventListener("click", () =>
  window.HelloBoardI18n.toggle(),
);
window.addEventListener("helloboard:language", () => {
  renderSidebarToggle();
  renderStatus();
  passwordHint();
  controls();
  renderSavedNetworks();
  renderNetworks();
  scanMessage(
    scanning
      ? "正在发现附近的网络…"
      : networks.length
        ? t("{count} 个网络", { count: networks.length })
        : lastScanMessage,
  );
  if (status && !$("#notice").hidden) notice(status.message);
  $("#panel-title").textContent = t(panelTitles[activePanel]);
  $("#show-password").setAttribute(
    "aria-label",
    t($("#password").type === "text" ? "隐藏密码" : "显示密码"),
  );
  $("#show-ap-password").setAttribute(
    "aria-label",
    t($("#ap-password").type === "text" ? "隐藏 AP 密码" : "显示 AP 密码"),
  );
});
window.HelloBoardI18n.applyStatic();
