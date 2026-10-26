"use strict";
(() => {
  const { t } = window.HelloBoardI18n;
  const $ = (selector) => document.querySelector(selector);
  const text = (selector, value) => {
    $(selector).textContent = value;
  };
  let latest = null;
  let samples = [];
  let historyId = null;
  let timer = null;
  let request = null;
  let manualRefreshing = false;
  let refreshQueued = false;
  let failed = false;
  let panel = "help";
  const known = (value) => typeof value === "number" && Number.isFinite(value);
  const decimal = (value, digits = 1) =>
    known(value)
      ? value.toLocaleString(
          window.HelloBoardI18n.language === "en" ? "en-US" : "zh-CN",
          { maximumFractionDigits: digits },
        )
      : "—";
  const percent = (value) => (known(value) ? decimal(value) + "%" : "—");
  function bytes(value) {
    if (!known(value)) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    return decimal(value, unit ? 1 : 0) + " " + units[unit];
  }
  const speed = (value) => (known(value) ? bytes(value) + "/s" : "—");
  function duration(value) {
    if (!known(value)) return "—";
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return t("{days} 天 {hours} 时 {minutes} 分", { days, hours, minutes });
  }
  const clock = (value) =>
    new Date(value * 1000).toLocaleTimeString(
      window.HelloBoardI18n.language === "en" ? "en-GB" : "zh-CN",
      { hour12: false },
    );
  function node(tag, content, className) {
    const element = document.createElement(tag);
    if (content !== undefined) element.textContent = content;
    if (className) element.className = className;
    return element;
  }
  function statusBadge(label, tone = "neutral") {
    const badge = node("span", t(label), "badge status-badge");
    badge.dataset.tone = tone;
    return badge;
  }
  function rows(container, values) {
    const list = typeof container === "string" ? $(container) : container;
    list.replaceChildren(
      ...values.map(([label, value]) => {
        const row = node("div");
        const detail = node("dd");
        if (value instanceof Node) detail.append(value);
        else detail.textContent = value ?? "—";
        row.append(node("dt", t(label)), detail);
        return row;
      }),
    );
  }
  function donut(element, value) {
    const available = known(value);
    element.dataset.available = String(available);
    const portion = available ? Math.max(0, Math.min(100, value)) : 0;
    element.setAttribute("stroke-dasharray", `${portion} 100`);
  }
  // Keep the SVG nodes alive between samples so ring changes can interpolate.
  const resourceGauges = new Map();
  function resourceGauge(id, label, value, tone = "cpu") {
    if (!resourceGauges.has(id)) {
      const wrapper = node("div", undefined, "resource-ring");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 100 100");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      for (const className of ["donut-track", "donut-value"]) {
        const circle = document.createElementNS(svg.namespaceURI, "circle");
        for (const [name, value] of Object.entries({
          cx: 50,
          cy: 50,
          r: 40,
          pathLength: 100,
        }))
          circle.setAttribute(name, value);
        circle.setAttribute("class", className);
        svg.append(circle);
      }
      const amount = node("span", "—", "resource-percent");
      wrapper.append(svg, amount);
      resourceGauges.set(id, { wrapper, amount, arc: svg.lastChild });
    }
    const gauge = resourceGauges.get(id);
    gauge.wrapper.dataset.tone = tone;
    gauge.wrapper.setAttribute("role", "img");
    gauge.wrapper.setAttribute("aria-label", `${label} · ${percent(value)}`);
    gauge.wrapper.title = `${label} · ${percent(value)}`;
    gauge.amount.textContent = known(value) ? `${Math.round(value)}%` : "—";
    donut(gauge.arc, value);
    return gauge.wrapper;
  }
  function reconcile(container, elements) {
    const keep = new Set(elements);
    elements.forEach((element, index) => {
      if (container.children[index] !== element)
        container.insertBefore(element, container.children[index] || null);
    });
    for (const child of [...container.children])
      if (!keep.has(child)) child.remove();
  }
  const coreNodes = new Map(),
    volumeNodes = new Map();
  function renderResources(cpu, mem, volumes) {
    const coreItems = cpu.cores.map((core) => {
      if (!coreNodes.has(core.name)) {
        const item = node("div", undefined, "core-item");
        item.append(node("span", core.name.toUpperCase(), "core-name"));
        coreNodes.set(core.name, item);
      }
      const item = coreNodes.get(core.name);
      const gauge = resourceGauge(
        `core:${core.name}`,
        core.name.toUpperCase(),
        core.percent,
      );
      if (item.firstChild !== gauge) item.prepend(gauge);
      return item;
    });
    reconcile($("#core-list"), coreItems);
    for (const [name] of coreNodes)
      if (!cpu.cores.some((core) => core.name === name)) {
        coreNodes.delete(name);
        resourceGauges.delete(`core:${name}`);
      }
    const memory = $("#memory-gauge");
    if (!memory.lastChild) {
      const copy = node("div", undefined, "resource-copy");
      copy.append(node("strong"), node("p"));
      memory.append(copy);
    }
    const memoryCopy = memory.lastChild;
    memoryCopy.firstChild.textContent = t("内存");
    memoryCopy.lastChild.textContent = `${bytes(mem.used)} / ${bytes(mem.total)}`;
    const gauge = resourceGauge("memory", t("内存"), mem.percent, "memory");
    if (memory.firstChild !== gauge) memory.prepend(gauge);
    reconcile(
      $("#volume-list"),
      volumes.map((volume) => {
        if (!volumeNodes.has(volume.mount)) {
          const item = node("div", undefined, "volume-item resource-summary");
          const copy = node("div", undefined, "resource-copy");
          copy.append(
            node("strong"),
            node("p"),
            node("p", undefined, "volume-note"),
          );
          item.append(copy);
          volumeNodes.set(volume.mount, item);
        }
        const item = volumeNodes.get(volume.mount),
          copy = item.lastChild;
        copy.children[0].textContent = volume.mount;
        copy.children[1].textContent = `${bytes(volume.used)} / ${bytes(volume.total)}`;
        copy.children[2].textContent = `${t("可用")} ${bytes(volume.available)} · ${volume.filesystem}`;
        copy.title = `${volume.filesystem} · ${volume.source}`;
        const gauge = resourceGauge(
          `volume:${volume.mount}`,
          volume.mount,
          volume.percent,
          "storage",
        );
        if (item.firstChild !== gauge) item.prepend(gauge);
        return item;
      }),
    );
    for (const [mount] of volumeNodes)
      if (!volumes.some((volume) => volume.mount === mount)) {
        volumeNodes.delete(mount);
        resourceGauges.delete(`volume:${mount}`);
      }
  }
  function totalRate(key) {
    const values = latest.interfaces.map((item) => item[key]).filter(known);
    return values.length ? values.reduce((a, b) => a + b, 0) : null;
  }
  function freshness() {
    const state = failed ? "error" : latest ? "live" : "loading";
    const labels = {
      error: latest ? "更新中断" : "暂时无法读取",
      live: "实时更新",
      loading: "读取中",
    };
    text("#update-state", t(labels[state]));
    $("#update-state").dataset.state = state;
    $("#update-state").dataset.tone =
      state === "live" ? "positive" : state === "error" ? "warning" : "neutral";
    $("#updated-at").textContent = latest ? clock(latest.sampled_at) : "—";
    if (latest)
      $("#updated-at").dateTime = new Date(
        latest.sampled_at * 1000,
      ).toISOString();
    refreshControl();
  }
  function refreshControl() {
    const button = $("#refresh-status");
    const label = t(manualRefreshing ? "刷新中" : "刷新状态");
    button.setAttribute("aria-label", label);
    button.title = label;
    button.disabled = manualRefreshing;
    button.setAttribute("aria-busy", String(manualRefreshing));
    button.classList.toggle("spinning", manualRefreshing);
  }
  function chart(id, first, second, maximum) {
    const svg = $("#" + id + "-chart");
    const start = samples[0]?.time ?? 0;
    const end = samples.at(-1)?.time ?? start;
    const span = Math.max(2, end - start);
    [first, second].forEach((key, index) => {
      let previous = null;
      const points = [];
      for (const sample of samples) {
        const value = sample[key];
        if (!known(value)) {
          previous = null;
          points.push(null);
          continue;
        }
        if (previous !== null && sample.time - previous > 10) points.push(null);
        previous = sample.time;
        const x = ((sample.time - start) / span) * 596 + 2;
        const y = 178 - (Math.min(maximum, Math.max(0, value)) / maximum) * 176;
        points.push([x, y]);
      }
      window.HelloBoardCharts.draw(
        svg.querySelector(index ? ".series-secondary" : ".series-primary"),
        points,
      );
    });
    $("#" + id + "-empty").hidden =
      samples.filter((s) => known(s[first]) || known(s[second])).length >= 2;
    text(
      "#" + id + "-period",
      samples.length > 1 ? clock(start) + " – " + clock(end) : "—",
    );
  }
  function render() {
    freshness();
    if (!latest) return;
    const d = latest,
      cpu = d.cpu,
      mem = d.memory,
      root = d.volumes.find((v) => v.mount === (d.primary_mount || "/")) || d.volumes[0];
    text("#device-summary", d.device.hostname + " · " + d.device.model);
    text("#metric-cpu", percent(cpu.percent));
    text(
      "#cpu-detail",
      t("{count} 核", { count: cpu.count }) +
        " · " +
        (known(cpu.frequency_mhz)
          ? decimal(cpu.frequency_mhz / 1000, 2) + " GHz"
          : "—"),
    );
    text("#metric-memory", percent(mem.percent));
    text("#memory-detail", bytes(mem.used) + " / " + bytes(mem.total));
    text("#metric-storage", percent(root?.percent));
    text(
      "#storage-detail",
      root ? bytes(root.used) + " / " + bytes(root.total) : t("暂无数据"),
    );
    text(
      "#metric-temperature",
      known(d.temperature_c) ? decimal(d.temperature_c) + "°C" : "—",
    );
    text(
      "#temperature-detail",
      t("风扇") +
        " · " +
        (d.fans.length
          ? d.fans.map((f) => decimal(f.rpm, 0) + " RPM").join(" / ")
          : "—"),
    );
    donut($("#meter-cpu"), cpu.percent);
    donut($("#meter-memory"), mem.percent);
    donut($("#meter-storage"), root?.percent);
    text("#cpu-current", percent(cpu.percent));
    text("#memory-current", percent(mem.percent));
    text("#rx-current", speed(totalRate("rx_rate")));
    text("#tx-current", speed(totalRate("tx_rate")));
    chart("usage", "cpu", "memory", 100);
    const networkMax = Math.max(
      1024,
      ...samples.flatMap((s) => [s.rx, s.tx]).filter(known),
    );
    chart("traffic", "rx", "tx", networkMax);
    text("#traffic-scale", "0 – " + speed(networkMax));
    renderResources(cpu, mem, d.volumes);
    rows("#resources-list", [
      [
        "系统负载",
        cpu.load.length ? cpu.load.map((v) => decimal(v, 2)).join(" / ") : "—",
      ],
      ["可用内存", bytes(mem.available)],
      ["缓存", bytes(mem.cached)],
      ["缓冲区", bytes(mem.buffers)],
      ["交换空间", bytes(mem.swap_used) + " / " + bytes(mem.swap_total)],
      ["进程数量", decimal(d.process_count, 0)],
    ].filter(([label]) => !(["缓存", "缓冲区"].includes(label) && mem[label === "缓存" ? "cached" : "buffers"] == null)
      && !(label === "系统负载" && !cpu.load.length)));
    rows("#device-list", [
      ["主机名", d.device.hostname],
      ["型号", d.device.model],
      ["系统", d.device.os],
      ["内核", d.device.kernel],
      ["架构", d.device.architecture],
      ["运行时间", duration(d.uptime_seconds)],
    ]);
    const power = d.power;
    $("#health-list").closest("section").hidden = !power && !d.fans.length;
    $("#metric-temperature").closest("article").hidden = !known(d.temperature_c) && !d.fans.length;
    $(".overview-grid").classList.toggle("without-temperature", !known(d.temperature_c) && !d.fans.length);
    $("#service-list").closest("section").hidden = !d.services.length;
    const limits = power
      ? [
          ["undervoltage", "欠压"],
          ["frequency_capped", "频率受限"],
          ["throttled", "降频"],
          ["temperature_limited", "温度限制"],
        ]
          .filter(([key]) => power[key])
          .map(([, label]) => t(label))
      : [];
    rows("#health-list", [
      [
        "供电与降频",
        power
          ? statusBadge(
              limits.join(" · ") || "正常",
              limits.length ? "warning" : "positive",
            )
          : "—",
      ],
      [
        "历史限制",
        power
          ? statusBadge(
              power.historical ? "曾发生" : "无",
              power.historical ? "warning" : "neutral",
            )
          : "—",
      ],
      ...d.fans.map((f) => ["风扇", decimal(f.rpm, 0) + " RPM"]),
    ]);
    rows(
      "#disk-list",
      d.disks.flatMap((disk) => [
        [disk.name, disk.type || "—"],
        ["读取速度", speed(disk.read_rate)],
        ["写入速度", speed(disk.write_rate)],
        ["累计读取", bytes(disk.read_bytes)],
        ["累计写入", bytes(disk.write_bytes)],
      ]),
    );
    $("#interface-list").replaceChildren(
      ...d.interfaces.map((iface) => {
        const item = node("div", undefined, "interface-item");
        const heading = node("div", undefined, "item-heading");
        const state =
          { up: "在线", down: "离线", dormant: "休眠", unknown: "未知" }[
            iface.state
          ] || "未知";
        heading.append(
          node(
            "strong",
            iface.name + (iface.wireless == null ? "" : " · " + (iface.wireless ? "WiFi" : t("有线"))),
          ),
          statusBadge(state, iface.state === "up" ? "positive" : "neutral"),
        );
        const list = node(
          "dl",
          undefined,
          "data-list compact-stats interface-stats",
        );
        rows(list, [
          ["地址", iface.addresses.join(" / ") || "—"],
          ...(iface.wireless
            ? [
                ["WiFi", iface.ssid || "—"],
                ["信号", percent(iface.signal)],
              ]
            : []),
          ["接收", speed(iface.rx_rate)],
          ["发送", speed(iface.tx_rate)],
          ["累计接收", bytes(iface.rx_bytes)],
          ["累计发送", bytes(iface.tx_bytes)],
          [
            "收发错误",
            decimal(iface.rx_errors, 0) + " / " + decimal(iface.tx_errors, 0),
          ],
        ]);
        for (const row of list.children)
          if ([t("地址"), "WiFi"].includes(row.firstChild.textContent))
            row.className = "wide-stat";
        item.append(heading, list);
        return item;
      }),
    );
    const serviceLabels = {
      active: "运行中",
      inactive: "未运行",
      failed: "故障",
      activating: "启动中",
      deactivating: "停止中",
      enabled: "已启用",
      disabled: "未启用",
      static: "静态",
      "enabled-runtime": "临时启用",
      manual: "手动",
    };
    $("#service-list").replaceChildren(
      ...d.services.map((service) => {
        const item = node("div", undefined, "service-item");
        const heading = node("div", undefined, "item-heading");
        heading.append(
          node(
            "strong",
            service.name.replace(/\.service$/, ""),
            "service-name",
          ),
          statusBadge(
            serviceLabels[service.state] || "未知",
            service.state === "active"
              ? "positive"
              : ["failed", "activating", "deactivating", "reloading"].includes(
                    service.state,
                  )
                ? "warning"
                : "neutral",
          ),
        );
        const list = node("dl", undefined, "data-list");
        rows(list, [
          [
            "开机自启",
            node(
              "span",
              t(serviceLabels[service.enabled] || service.enabled || "未知"),
              "muted",
            ),
          ],
        ]);
        item.append(heading, list);
        return item;
      }),
    );
    if (!d.services.length)
      $("#service-list").append(node("p", t("暂无数据"), "muted"));
  }
  async function update() {
    clearTimeout(timer);
    if (document.hidden || request) return;
    refreshQueued = false;
    const controller = new AbortController();
    request = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const query = new URLSearchParams();
      if (historyId && samples.length) {
        query.set("history_id", historyId);
        query.set("since", samples.at(-1).time);
      }
      const response = await fetch(
        "/api/system" + (query.size ? "?" + query : ""),
        {
          cache: "no-store",
          signal: controller.signal,
        },
      );
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (document.hidden) return;
      latest = data;
      failed = false;
      if (historyId !== data.history_id) {
        samples = [];
        historyId = data.history_id;
      }
      const merged = new Map(samples.map((sample) => [sample.time, sample]));
      for (const sample of data.history) merged.set(sample.time, sample);
      samples = [...merged.values()]
        .filter((sample) => sample.time >= data.sampled_at - 600)
        .sort((a, b) => a.time - b.time)
        .slice(-300);
      render();
      window.HelloBoardProcesses.refresh(manualRefreshing);
    } catch {
      if (!document.hidden) {
        failed = true;
        freshness();
      }
    } finally {
      clearTimeout(timeout);
      request = null;
      if (!refreshQueued) manualRefreshing = false;
      refreshControl();
      if (!document.hidden)
        timer = setTimeout(update, refreshQueued ? 0 : failed ? 5000 : 2000);
    }
  }
  $("#refresh-status").addEventListener("click", () => {
    manualRefreshing = true;
    refreshQueued = true;
    refreshControl();
    clearTimeout(timer);
    // If an automatic request is running, queue exactly one refresh after it.
    if (!request) update();
  });
  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    if (document.hidden) request?.abort();
    else update();
  });
  document.querySelectorAll("[data-panel]").forEach((button) =>
    button.addEventListener("click", () => {
      panel = button.dataset.panel;
      for (const name of ["help", "style"])
        $("#" + name + "-content").hidden = name !== panel;
      text("#panel-title", t(panel === "style" ? "样式设置" : "使用帮助"));
      showDialog($("#side-panel"));
    }),
  );
  $("#panel-close").addEventListener("click", () =>
    closeDialog($("#side-panel")),
  );
  $("#language-toggle").addEventListener("click", () =>
    window.HelloBoardI18n.toggle(),
  );
  window.addEventListener("helloboard:language", () => {
    text("#panel-title", t(panel === "style" ? "样式设置" : "使用帮助"));
    render();
  });
  window.HelloBoardI18n.applyStatic();
  update();
})();
