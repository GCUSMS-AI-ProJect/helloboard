"use strict";
// Small SVG renderer. The browser interpolates paths; no JavaScript frame loop.
window.HelloBoardCharts = (() => {
  const states = new WeakMap();
  const charts = new Map();
  const motion = matchMedia("(prefers-reduced-motion: reduce)");
  const ns = "http://www.w3.org/2000/svg";
  let stopped = false;
  const visible = new WeakMap();
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      visible.set(entry.target, entry.isIntersecting);
      sync(entry.target);
    }
  });
  function sync(svg) {
    if (stopped || document.hidden || !visible.get(svg)) svg.pauseAnimations();
    else svg.unpauseAnimations();
  }
  function path(points) {
    let previous = null;
    return points
      .map((point) => {
        if (!point) {
          previous = null;
          return "";
        }
        const [x, y] = point;
        // Horizontal tangent controls preserve each measured value, with no overshoot.
        const value = previous
          ? `C${((previous[0] + x) / 2).toFixed(2)},${previous[1].toFixed(2)} ${((previous[0] + x) / 2).toFixed(2)},${y.toFixed(2)} ${x.toFixed(2)},${y.toFixed(2)}`
          : `M${x.toFixed(2)},${y.toFixed(2)}`;
        previous = point;
        return value;
      })
      .join(" ");
  }
  function draw(element, points) {
    const svg = element.ownerSVGElement;
    if (!charts.has(svg)) {
      charts.set(svg, true);
      visible.set(svg, true);
      observer.observe(svg);
    }
    const target = path(points);
    const old = states.get(element);
    if (old?.target === target) return;
    element.querySelector("animate")?.remove();
    element.setAttribute("d", target);
    states.set(element, { target, points });
    if (
      !old ||
      motion.matches ||
      stopped ||
      document.hidden ||
      !visible.get(svg)
    )
      return;
    // Adding a sample changes the command count. Extend the previous path at its
    // endpoint so both paths can interpolate without jumping. Trim expired points.
    const previous = old.points.slice(-points.length);
    while (previous.length < points.length)
      previous.push(previous.at(-1) ?? null);
    const from = path(previous);
    if (
      !from.includes("C") ||
      !target.includes("C") ||
      from.replace(/[^MC]/g, "") !== target.replace(/[^MC]/g, "")
    )
      return;
    const animation = document.createElementNS(ns, "animate");
    for (const [key, value] of Object.entries({
      attributeName: "d",
      from,
      to: target,
      dur: "1.65s",
      begin: "indefinite",
      fill: "remove",
      calcMode: "spline",
      keyTimes: "0;1",
      keySplines: "0.25 0.1 0.25 1",
    }))
      animation.setAttribute(key, value);
    animation.addEventListener("endEvent", () => animation.remove(), {
      once: true,
    });
    element.append(animation);
    animation.beginElement();
    sync(svg);
  }
  function pause(value) {
    stopped = value;
    for (const svg of charts.keys()) sync(svg);
  }
  document.addEventListener("visibilitychange", () => {
    for (const svg of charts.keys()) sync(svg);
  });
  motion.addEventListener("change", () => {
    if (motion.matches)
      for (const svg of charts.keys())
        svg
          .querySelectorAll("animate")
          .forEach((animation) => animation.remove());
  });
  return { draw, pause };
})();
