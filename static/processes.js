"use strict";
(() => {
  const { t } = window.HelloBoardI18n;
  const $ = (selector) => document.querySelector(selector);
  const key = (item) => `${item.pid}:${item.started}`;
  const PAGE_SIZE = 6;
  let items = [],
    selected = new Map(),
    targets = [],
    visible = [];
  let sort = "cpu",
    page = 0,
    action = "terminate",
    busy = false,
    complete = false;
  let request = null,
    receivedAt = -Infinity,
    preview = true,
    supported = false,
    maxBatch = 32;
  let loadError = false,
    toastTimer;
  const rows = new Map();
  const dialog = $("#process-dialog");
  const text = (selector, value) => {
    $(selector).textContent = value;
  };
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(svg.namespaceURI, "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }
  function memory(value) {
    if (!Number.isFinite(value)) return "—";
    const units = ["B", "KiB", "MiB", "GiB"];
    let index = 0;
    while (value >= 1024 && index < 3) {
      value /= 1024;
      index++;
    }
    return (
      value.toLocaleString(
        window.HelloBoardI18n.language === "en" ? "en-US" : "zh-CN",
        { maximumFractionDigits: index ? 1 : 0 },
      ) +
      " " +
      units[index]
    );
  }
  const cpu = (value) =>
    Number.isFinite(value)
      ? value.toLocaleString(
          window.HelloBoardI18n.language === "en" ? "en-US" : "zh-CN",
          { maximumFractionDigits: 1 },
        ) + "%"
      : "—";
  function error(selector, message = "") {
    const element = $(selector);
    element.dataset.message = message;
    element.textContent = t(message);
    element.hidden = !message;
  }
  function makeRow() {
    const row = document.createElement("tr");
    const selectCell = document.createElement("td");
    selectCell.className = "process-select-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    const selection = document.createElement("span");
    selection.className = "process-check";
    const tick = icon("selection-tick");
    tick.classList.add("process-check-tick");
    selection.append(checkbox, tick);
    selectCell.append(selection);
    const nameCell = document.createElement("td");
    nameCell.className = "process-name-cell";
    const name = document.createElement("span");
    name.className = "process-name";
    const pidNote = document.createElement("span");
    pidNote.className = "process-mobile-note";
    nameCell.append(name, pidNote);
    const pidCell = document.createElement("td");
    pidCell.className = "process-pid-cell";
    const cpuCell = document.createElement("td");
    cpuCell.className = "process-cpu-cell";
    const memoryCell = document.createElement("td");
    memoryCell.className = "process-memory-cell";
    const mem = document.createElement("span"),
      cpuNote = document.createElement("span");
    cpuNote.className = "process-mobile-note";
    memoryCell.append(mem, cpuNote);
    const actionCell = document.createElement("td");
    actionCell.className = "process-action-cell";
    const more = document.createElement("button");
    more.type = "button";
    more.className = "icon-button process-more";
    more.append(icon("more"));
    actionCell.append(more);
    row.append(selectCell, nameCell, pidCell, cpuCell, memoryCell, actionCell);
    return {
      row,
      checkbox,
      name,
      pidNote,
      pidCell,
      cpuCell,
      mem,
      cpuNote,
      more,
    };
  }
  function render() {
    const query = $("#process-search").value.trim().toLocaleLowerCase();
    const filtered = items.filter(
      (item) =>
        item.name.toLocaleLowerCase().includes(query) ||
        String(item.pid).includes(query),
    );
    filtered.sort(
      (a, b) =>
        (sort === "cpu"
          ? (b.cpu_percent ?? -1) - (a.cpu_percent ?? -1)
          : b.memory - a.memory) || a.pid - b.pid,
    );
    const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    page = Math.min(page, pages - 1);
    visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    const body = $("#process-list"),
      keep = new Set();
    visible.forEach((item, index) => {
      const id = key(item);
      keep.add(id);
      if (!rows.has(id)) rows.set(id, makeRow());
      const r = rows.get(id);
      r.row.dataset.key = id;
      r.row.dataset.selected = String(selected.has(id));
      r.row.dataset.selectable = String(Boolean(item.selectable));
      r.row.title = t(item.reason || "");
      r.checkbox.dataset.key = id;
      r.checkbox.checked = selected.has(id);
      r.checkbox.disabled =
        !item.selectable || (!selected.has(id) && selected.size >= maxBatch);
      r.checkbox.setAttribute(
        "aria-label",
        t("选择进程 {name}", { name: item.name + " · " + item.pid }),
      );
      r.checkbox.title = t(item.reason || "选择进程");
      r.name.textContent = item.name;
      r.name.title = item.name;
      r.pidNote.textContent = String(item.pid);
      r.pidCell.textContent = item.pid;
      r.cpuCell.textContent = cpu(item.cpu_percent);
      r.mem.textContent = memory(item.memory);
      r.cpuNote.textContent = `CPU ${cpu(item.cpu_percent)}`;
      r.more.dataset.key = id;
      r.more.disabled = !item.selectable;
      const label = item.reason
        ? t(item.reason)
        : t("终止进程 {name}", { name: item.name + " · " + item.pid });
      r.more.setAttribute("aria-label", label);
      r.more.title = label;
      if (body.children[index] !== r.row)
        body.insertBefore(r.row, body.children[index] || null);
    });
    for (const child of [...body.children])
      if (!keep.has(child.dataset.key)) child.remove();
    for (const [id] of rows) if (!keep.has(id)) rows.delete(id);
    if (!visible.length) {
      const row = document.createElement("tr"),
        cell = document.createElement("td");
      cell.colSpan = 6;
      cell.className = "process-empty";
      cell.textContent = t(
        loadError
          ? "进程列表暂时不可用"
          : query
            ? "没有匹配的进程"
            : "正在读取进程",
      );
      row.append(cell);
      body.append(row);
    }
    const eligible = visible.filter((item) => item.selectable);
    const checked = eligible.filter((item) => selected.has(key(item))).length;
    const all = $("#process-select-all");
    all.checked = eligible.length > 0 && checked === eligible.length;
    all.indeterminate = checked > 0 && checked < eligible.length;
    all.disabled = !eligible.length;
    text(
      "#process-count",
      selected.size
        ? t("已选 {selected} · 共 {count} 个", {
            selected: selected.size,
            count: filtered.length,
          })
        : t("共 {count} 个", { count: filtered.length }),
    );
    text("#process-page", `${page + 1} / ${pages}`);
    $("#process-prev").disabled = page === 0;
    $("#process-next").disabled = page >= pages - 1;
    $("#process-clear").hidden = !selected.size;
    $("#terminate-selected").disabled = !selected.size;
    for (const name of ["cpu", "memory"])
      $("#sort-" + name).setAttribute("aria-pressed", String(sort === name));
    error("#process-error", loadError ? "进程列表更新中断" : "");
  }
  async function refresh(force = false) {
    if (
      document.hidden ||
      request ||
      (!force && performance.now() - receivedAt < 5500)
    )
      return;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch("/api/processes", {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (document.hidden) return;
      items = data.items;
      preview = data.preview;
      supported = data.supported;
      maxBatch = data.max_batch;
      receivedAt = performance.now();
      loadError = false;
      const live = new Map(items.map((item) => [key(item), item]));
      for (const [id] of selected) {
        if (!live.get(id)?.selectable) selected.delete(id);
        else selected.set(id, live.get(id));
      }
      render();
    } catch {
      if (!document.hidden) {
        receivedAt = performance.now();
        loadError = true;
        render();
      }
    } finally {
      clearTimeout(timeout);
      request = null;
    }
  }
  function method() {
    for (const button of document.querySelectorAll("#process-method button"))
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.action === action),
      );
    text(
      "#process-method-note",
      t(
        action === "kill"
          ? "立即强制终止，未保存的数据可能丢失。"
          : "请求进程正常退出；进程可能需要时间或拒绝退出。",
      ),
    );
  }
  function controls() {
    $("#process-submit").disabled =
      busy || (!complete && (preview || !supported));
    text(
      "#process-submit",
      t(complete ? "关闭" : busy ? "正在执行…" : "验证并终止"),
    );
    $("#process-submit").setAttribute("aria-busy", String(busy));
    for (const id of ["process-username", "process-password"])
      $("#" + id).disabled = busy || complete;
    for (const button of document.querySelectorAll("#process-method button"))
      button.disabled = busy || complete;
    $("#process-dialog-close").disabled = busy;
    $("#process-cancel").disabled = busy;
    $("#process-cancel").hidden = complete;
  }
  function open(chosen) {
    if (!chosen.length) return;
    targets = chosen.map((item) => ({ ...item }));
    action = "terminate";
    complete = false;
    const list = $("#process-targets");
    list.replaceChildren();
    for (const item of targets) {
      const entry = document.createElement("li");
      entry.textContent = `${item.name} · ${item.pid}`;
      list.append(entry);
    }
    $("#process-password").value = "";
    $("#process-results").hidden = true;
    $("#process-results").replaceChildren();
    error(
      "#process-dialog-error",
      preview
        ? "预览模式不允许终止进程。"
        : !supported
          ? "当前系统不支持安全终止进程。"
          : "",
    );
    method();
    controls();
    showDialog(dialog);
    if (!preview && supported)
      $("#process-password").focus({ preventScroll: true });
  }
  function notify(message) {
    const toast = $("#toast");
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add("visible"));
    toastTimer = setTimeout(() => {
      toast.classList.remove("visible");
      toastTimer = setTimeout(() => {
        toast.hidden = true;
      }, 150);
    }, 2000);
  }
  $("#process-search").addEventListener("input", () => {
    page = 0;
    render();
  });
  for (const name of ["cpu", "memory"])
    $("#sort-" + name).addEventListener("click", () => {
      sort = name;
      page = 0;
      render();
    });
  $("#process-prev").addEventListener("click", () => {
    page--;
    render();
  });
  $("#process-next").addEventListener("click", () => {
    page++;
    render();
  });
  $("#process-clear").addEventListener("click", () => {
    selected.clear();
    render();
  });
  $("#process-list").addEventListener("change", (event) => {
    const item = visible.find((item) => key(item) === event.target.dataset.key);
    if (!item?.selectable) return;
    if (event.target.checked && selected.size < maxBatch)
      selected.set(key(item), item);
    else selected.delete(key(item));
    render();
  });
  $("#process-select-all").addEventListener("change", (event) => {
    for (const item of visible.filter((item) => item.selectable)) {
      if (!event.target.checked) selected.delete(key(item));
      else if (selected.size < maxBatch) selected.set(key(item), item);
    }
    render();
  });
  $("#process-list").addEventListener("click", (event) => {
    const button = event.target.closest(".process-more");
    if (button && !button.disabled)
      open(visible.filter((item) => key(item) === button.dataset.key));
  });
  $("#terminate-selected").addEventListener("click", () =>
    open([...selected.values()]),
  );
  for (const id of ["process-dialog-close", "process-cancel"])
    $("#" + id).addEventListener("click", () => closeDialog(dialog));
  dialog.addEventListener("close", () => {
    $("#process-password").value = "";
    targets = [];
  });
  window.HelloBoardCanCloseDialog = (current) => current !== dialog || !busy;
  for (const button of document.querySelectorAll("#process-method button"))
    button.addEventListener("click", () => {
      action = button.dataset.action;
      method();
    });
  $("#process-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (complete) {
      closeDialog(dialog);
      return;
    }
    if (busy || preview || !supported) return;
    busy = true;
    controls();
    error("#process-dialog-error");
    const controller = new AbortController(),
      timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/processes/terminate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": $("meta[name=csrf-token]").content,
        },
        body: JSON.stringify({
          action,
          targets: targets.map(({ pid, started }) => ({ pid, started })),
          username: $("#process-username").value,
          password: $("#process-password").value,
        }),
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) {
        error(
          "#process-dialog-error",
          data.error || "操作未完成，请稍后重试。",
        );
        return;
      }
      let sent = 0;
      for (const result of data.results) {
        if (["sent", "exited"].includes(result.status))
          selected.delete(key(result));
        if (result.status === "sent") sent++;
      }
      complete = true;
      const unsuccessful = data.results.filter(
        (result) => !["sent", "exited"].includes(result.status),
      );
      if (!unsuccessful.length) {
        await closeDialog(dialog);
        notify(
          sent
            ? t(
                action === "kill"
                  ? "已向 {count} 个进程发送强制终止信号"
                  : "已向 {count} 个进程发送退出请求",
                { count: sent },
              )
            : t("进程已退出"),
        );
      } else {
        const list = $("#process-results");
        list.replaceChildren();
        for (const result of data.results) {
          const line = document.createElement("p");
          line.dataset.message = result.message;
          line.dataset.pid = result.pid;
          line.textContent = `PID ${result.pid} · ${t(result.message)}`;
          list.append(line);
        }
        list.hidden = false;
      }
      render();
      refresh(true);
    } catch {
      error("#process-dialog-error", "结果暂时无法确认，请刷新列表后查看。");
    } finally {
      clearTimeout(timeout);
      $("#process-password").value = "";
      busy = false;
      controls();
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) request?.abort();
  });
  window.addEventListener("helloboard:language", () => {
    render();
    method();
    controls();
    const e = $("#process-dialog-error");
    error("#process-dialog-error", e.dataset.message || "");
    for (const line of document.querySelectorAll("#process-results p"))
      line.textContent = `PID ${line.dataset.pid} · ${t(line.dataset.message)}`;
  });
  window.HelloBoardProcesses = { refresh };
})();
