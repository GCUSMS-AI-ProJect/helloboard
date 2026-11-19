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
function cancelTest() {
  testRequest?.abort();
  if (el("proxy-test").open) el("proxy-test").close();
}
el("cancel-test").onclick = cancelTest;
el("proxy-test").addEventListener("cancel", cancelTest);
async function save() {
  const submit = el("proxy-form").querySelector("button[type=submit]");
  if (submit.disabled) return;
  submit.disabled = true;
  try {
    const settings = {enabled: mode.dataset.mode === "on", host: el("host").value.trim(), port: el("port").valueAsNumber};
    if (settings.enabled) {
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
    await post("bash-proxy", settings);
    feedback(settings.enabled ? t("Successful · 联网成功，已保存") : t("代理已关闭"));
  } catch (error) {
    if (error.name === "AbortError") { feedback(t("已取消")); return; }
    if (error.login) { el("auth-error").textContent = ""; el("login").showModal(); el("password").focus(); }
    else feedback(error.message);
  } finally { submit.disabled = false; }
}
el("proxy-form").onsubmit = event => { event.preventDefault(); save(); };
el("auth-form").onsubmit = async event => {
  event.preventDefault();
  try {
    await post("authorize", {username: el("username").value, password: el("password").value});
    el("login").close();
    await save();
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
