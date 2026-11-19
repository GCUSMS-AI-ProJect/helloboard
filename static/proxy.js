"use strict";
const el = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const t = window.HelloBoardI18n.t;
async function post(path, body) {
  const response = await fetch("/api/" + path, {
    method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error), {login: data.authorization_required});
  return data;
}
async function save() {
  el("result").textContent = "";
  try {
    await post("bash-proxy", {enabled: el("enabled").checked, host: el("host").value.trim(), port: el("port").valueAsNumber});
    el("result").textContent = t("已保存");
  } catch (error) {
    if (error.login) { el("auth-error").textContent = ""; el("login").showModal(); el("password").focus(); }
    else el("result").textContent = error.message;
  }
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
