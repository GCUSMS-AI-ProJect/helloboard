"use strict";
const el = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const t = window.HelloBoardI18n.t;
const mode = el("proxy-mode");
let toastTimer;
function feedback(message) {
  clearTimeout(toastTimer);
  el("result").textContent = message;
  el("result").classList.add("visible");
  toastTimer = setTimeout(() => el("result").classList.remove("visible"), 2000);
}
for (const button of mode.querySelectorAll("button")) {
  button.onclick = () => {
    if (mode.dataset.mode === button.dataset.value) return;
    mode.dataset.mode = button.dataset.value;
    for (const item of mode.querySelectorAll("button")) {
      item.classList.toggle("selected", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    }
    feedback(t("点击保存设置以应用"));
  };
}
async function post(path, body, signal) {
  const response = await fetch("/api/" + path, {
    method: "POST", signal, headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error), {login: data.authorization_required});
  return data;
}
let testRequest;
let pendingSave;
const form = el("proxy-form");
const saveButton = form.querySelector("button[type=submit]");
const testButton = el("test-connection");
function cancelTest() {
  testRequest?.abort();
  if (el("proxy-test").open) el("proxy-test").close();
}
el("cancel-test").onclick = cancelTest;
el("proxy-test").addEventListener("cancel", cancelTest);
async function applySettings(save) {
  if (saveButton.disabled) return;
  const enabled = mode.dataset.mode === "on";
  const host = el("host").value.trim();
  el("host").required = enabled || !save;
  if (!form.reportValidity()) return;
  const settings = {enabled, host, port: el("port").valueAsNumber};
  if (el("protocol")) {
    settings.protocol = el("protocol").value;
    settings.bypass = el("bypass").value.trim();
    settings.timeout = el("timeout").valueAsNumber;
  }
  saveButton.disabled = testButton.disabled = true;
  try {
    if (enabled || !save) {
      testRequest = new AbortController();
      el("proxy-test").showModal();
      try {
        await post("bash-proxy/test", settings, testRequest.signal);
        testRequest.signal.throwIfAborted();
      } finally {
        if (el("proxy-test").open) el("proxy-test").close();
        testRequest = null;
      }
    }
    if (save) {
      await post("bash-proxy", settings);
      feedback(t(enabled ? "Successful · 联网成功，已保存" : "代理已关闭"));
    } else feedback(t("代理连接成功"));
  } catch (error) {
    if (error.name === "AbortError") { feedback(t("已取消")); return; }
    if (error.login) {
      pendingSave = save;
      el("auth-error").textContent = "";
      el("login").showModal();
      el("password").focus();
    } else feedback(error.message);
  } finally {
    saveButton.disabled = testButton.disabled = false;
  }
}
form.noValidate = true;
form.onsubmit = event => { event.preventDefault(); applySettings(true); };
testButton.onclick = () => applySettings(false);
el("auth-form").onsubmit = async event => {
  event.preventDefault();
  try {
    await post("authorize", {username: el("username").value, password: el("password").value});
    el("login").close();
    await applySettings(pendingSave);
  } catch (error) { el("auth-error").textContent = error.message; }
  finally { el("password").value = ""; }
};
el("cancel").onclick = () => el("login").close();
for (const button of document.querySelectorAll("[data-panel]")) {
  button.onclick = () => {
    const style = button.dataset.panel === "style";
    el("style-content").hidden = !style;
    el("help-content").hidden = style;
    el("panel-title").textContent = button.title;
    el("side-panel").showModal();
  };
}
el("panel-close").onclick = () => el("side-panel").close();
