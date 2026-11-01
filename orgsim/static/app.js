(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const NS = "http://www.w3.org/2000/svg";
  const BEHAVIOR_COLORS = {
    operator: "#62c6b8",
    careerist: "#e8b45a",
    loyalist: "#83a9e6",
    politician: "#df7b68",
    steady: "#b7a1e2",
  };
  const METRICS = {
    weighted_height: {
      label: "Hierarchy height",
      short: "Height",
      color: "#e8b45a",
      format: (v) => `${Number(v).toFixed(2)}`,
      axis: (v) => Number(v).toFixed(1),
    },
    weighted_manager_ratio: {
      label: "Manager ratio",
      short: "Managers",
      color: "#df7b68",
      format: (v) => `${(Number(v) * 100).toFixed(1)}%`,
      axis: (v) => `${(Number(v) * 100).toFixed(0)}%`,
    },
    output_per_worker: {
      label: "Output per worker",
      short: "Output",
      color: "#62c6b8",
      format: (v) => Number(v).toFixed(1),
      axis: (v) => Number(v).toFixed(0),
    },
    avg_firm_size: {
      label: "Average firm size",
      short: "Firm size",
      color: "#83a9e6",
      format: (v) => Number(v).toFixed(1),
      axis: (v) => Number(v).toFixed(0),
    },
    wage_per_worker: {
      label: "Wage per worker",
      short: "Wage",
      color: "#b7a1e2",
      format: (v) => Number(v).toFixed(1),
      axis: (v) => Number(v).toFixed(0),
    },
    profit_margin: {
      label: "Profit margin",
      short: "Margin",
      color: "#9bc27a",
      format: (v) => `${(Number(v) * 100).toFixed(1)}%`,
      axis: (v) => `${(Number(v) * 100).toFixed(0)}%`,
    },
  };
  const CONDITION_LABELS = {
    taller_hierarchy: "Taller hierarchy",
    lower_productivity: "Lower output per worker",
    not_much_smaller: "Still large",
    not_selected_out: "Not selected out",
  };

  const state = {
    scenarios: [],
    result: null,
    experiment: null,
    metric: "weighted_height",
    selectedFirm: null,
    busy: false,
    runStarted: 0,
  };

  const els = {
    scenario: $("#scenario"),
    scenarioChip: $("#scenarioChip"),
    scenarioDescription: $("#scenarioDescription"),
    population: $("#population"),
    populationOut: $("#populationOut"),
    steps: $("#steps"),
    stepsOut: $("#stepsOut"),
    seed: $("#seed"),
    replicates: $("#replicates"),
    runBtn: $("#runBtn"),
    compareBtn: $("#compareBtn"),
    heroCompare: $("#heroCompare"),
    statusLight: $("#statusLight"),
    statusText: $("#statusText"),
    runMeta: $("#runMeta"),
    kpiHeight: $("#kpiHeight"),
    kpiManagers: $("#kpiManagers"),
    kpiOutput: $("#kpiOutput"),
    kpiDiscount: $("#kpiDiscount"),
    kpiSize: $("#kpiSize"),
    kpiSurvival: $("#kpiSurvival"),
    chart: $("#chart"),
    chartCaption: $("#chartCaption"),
    metricChips: $("#metricChips"),
    firmSelect: $("#firmSelect"),
    treeMeta: $("#treeMeta"),
    tree: $("#tree"),
    events: $("#events"),
    eventCount: $("#eventCount"),
    verdictTitle: $("#verdictTitle"),
    verdictBadge: $("#verdictBadge"),
    verdictBody: $("#verdictBody"),
    compareSection: $("#compareSection"),
    compareMeta: $("#compareMeta"),
    compareTable: $("#compareTable"),
    compareBars: $("#compareBars"),
    tooltip: $("#tooltip"),
  };

  // ------------------------------------------------------------------
  // Utilities
  // ------------------------------------------------------------------
  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function pct(value, digits = 1) {
    return `${(Number(value || 0) * 100).toFixed(digits)}%`;
  }

  function num(value, digits = 1) {
    return Number(value || 0).toFixed(digits);
  }

  function signed(value, digits = 2) {
    const n = Number(value || 0);
    return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
  }

  function signedPct(value, digits = 1) {
    const n = Number(value || 0) * 100;
    return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
  }

  function debounce(fn, delay = 140) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function svg(tag, attrs = {}, text = null) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value !== undefined && value !== null) node.setAttribute(key, value);
    });
    if (text !== null) node.textContent = text;
    return node;
  }

  function setStatus(kind, message) {
    els.statusLight.className = `status-light ${kind}`;
    els.statusText.textContent = message;
  }

  function setBusy(busy, label = "Running model…") {
    state.busy = busy;
    els.runBtn.disabled = busy;
    els.compareBtn.disabled = busy;
    els.runBtn.classList.toggle("loading", busy);
    if (busy) {
      els.runBtn.querySelector(".button-label").textContent = label;
      els.runBtn.querySelector(".button-spinner").style.display = "inline-block";
      setStatus("working", label);
    } else {
      els.runBtn.querySelector(".button-label").textContent = "Run simulation";
      els.runBtn.querySelector(".button-spinner").style.display = "none";
    }
  }

  function showError(message) {
    setStatus("error", message);
    els.runMeta.textContent = "error";
    console.error(message);
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data;
  }

  function tooltipAt(event, html) {
    els.tooltip.innerHTML = html;
    const pad = 14;
    const width = 260;
    const x = Math.min(window.innerWidth - width - 12, event.clientX + pad);
    const y = Math.max(10, event.clientY - 10);
    els.tooltip.style.left = `${x}px`;
    els.tooltip.style.top = `${y}px`;
    els.tooltip.classList.add("show");
  }

  function hideTooltip() {
    els.tooltip.classList.remove("show");
  }

  // ------------------------------------------------------------------
  // Setup
  // ------------------------------------------------------------------
  async function loadScenarios() {
    try {
      const response = await fetch("/api/scenarios");
      const data = await response.json();
      state.scenarios = data.scenarios || [];
    } catch (error) {
      console.error(error);
      state.scenarios = [
        { key: "baseline", label: "Career ladder + competition", description: "Workers value promotion prospects." },
        { key: "no_ladder", label: "No career-ladder preference", description: "Workers do not value promotion prospects." },
        { key: "no_competition", label: "Sheltered market", description: "Fixed price and little failure." },
        { key: "high_competition", label: "High competitive pressure", description: "More contested output market." },
        { key: "career_no_retention", label: "Career preference, no retention promotions", description: "Workers value ladders but firms do not create extra slots." },
      ];
    }

    els.scenario.innerHTML = state.scenarios
      .map((scenario) => `<option value="${esc(scenario.key)}">${esc(scenario.label)}</option>`)
      .join("");
    els.scenario.value = "baseline";
    updateScenarioCopy();
  }

  function updateScenarioCopy() {
    const scenario = state.scenarios.find((row) => row.key === els.scenario.value);
    if (!scenario) return;
    els.scenarioDescription.textContent = scenario.description;
    els.scenarioChip.textContent = scenario.key.replaceAll("_", " ");
  }

  function updateRangeOutput(input, output) {
    output.textContent = input.value;
  }

  // ------------------------------------------------------------------
  // Run
  // ------------------------------------------------------------------
  async function runSimulation(options = {}) {
    if (state.busy) return;
    const scenario = els.scenario.value;
    const steps = Number(els.steps.value);
    const population = Number(els.population.value);
    const seed = Number(els.seed.value);
    state.runStarted = performance.now();
    setBusy(true, "Running simulation…");
    try {
      const result = await postJSON("/api/run", { scenario, steps, population, seed });
      state.result = result;
      state.selectedFirm = null;
      renderAll();
      const elapsed = ((performance.now() - state.runStarted) / 1000).toFixed(1);
      setStatus("ready", `Complete — ${result.summary.final_firms} firms alive after ${result.history.length} steps.`);
      els.runMeta.textContent = `${elapsed}s · seed ${result.meta.seed} · price ${result.price.toFixed(2)}`;
    } catch (error) {
      showError(error.message || "Simulation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function compareHypothesis(options = {}) {
    if (state.busy) return;
    const steps = Number(els.steps.value);
    const population = Number(els.population.value);
    const seed = Number(els.seed.value);
    const replicates = Number(els.replicates.value);
    setBusy(true, "Running counterfactual…");
    try {
      const experiment = await postJSON("/api/compare", {
        steps,
        population,
        seed,
        replicates,
      });
      state.experiment = experiment;
      renderVerdict(experiment.hypothesis, experiment);
      renderComparison(experiment);
      setStatus(
        "ready",
        `Counterfactual complete — ${experiment.meta.seeds.length} seed${experiment.meta.seeds.length > 1 ? "s" : ""}, ${replicates > 1 ? "paired" : "single"} comparison.`
      );
      els.runMeta.textContent = `${experiment.meta.steps} steps · ${experiment.meta.population} workers`;
      if (!options || !options.silent) {
        document.querySelector("#evidence").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      showError(error.message || "Comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  function renderAll() {
    const result = state.result;
    if (!result) return;
    renderKpis();
    drawChart();
    populateFirmSelect();
    renderSelectedFirm();
    renderEvents();
  }

  function renderKpis() {
    const summary = state.result?.summary;
    const final = state.result?.final_step || {};
    if (!summary) {
      ["kpiHeight", "kpiManagers", "kpiOutput", "kpiDiscount", "kpiSize", "kpiSurvival"].forEach((key) => {
        els[key].textContent = "—";
      });
      return;
    }
    els.kpiHeight.innerHTML = `${num(final.weighted_height ?? summary.weighted_height, 2)}<span class="unit">levels</span>`;
    els.kpiManagers.textContent = pct(final.weighted_manager_ratio ?? summary.weighted_manager_ratio);
    els.kpiOutput.textContent = num(final.output_per_worker ?? summary.output_per_worker, 1);
    els.kpiDiscount.textContent = pct(final.career_discount ?? summary.career_discount);
    els.kpiSize.textContent = num(final.avg_firm_size ?? summary.avg_firm_size, 1);
    els.kpiSurvival.textContent = pct(summary.survival_rate, 0);
  }

  function drawChart() {
    const history = state.result?.history || [];
    const metric = METRICS[state.metric];
    els.chart.innerHTML = "";
    if (!history.length) {
      els.chart.innerHTML = '<div class="empty-state">No trajectory yet.</div>';
      return;
    }
    const values = history.map((row) => Number(row[state.metric] || 0));
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (max - min < 1e-9) {
      min -= 1;
      max += 1;
    }
    const range = max - min;
    min -= range * 0.12;
    max += range * 0.12;
    if (state.metric === "weighted_manager_ratio" || state.metric === "profit_margin") {
      min = Math.min(0, min);
    }

    const W = 960;
    const H = 280;
    const m = { l: 58, r: 22, t: 18, b: 34 };
    const plotW = W - m.l - m.r;
    const plotH = H - m.t - m.b;
    const x = (index) => (history.length <= 1 ? m.l + plotW / 2 : m.l + (index / (history.length - 1)) * plotW);
    const y = (value) => m.t + plotH - ((value - min) / (max - min)) * plotH;

    const root = svg("svg", {
      class: "chart-svg",
      viewBox: `0 0 ${W} ${H}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label": `${metric.label} over time`,
    });
    const defs = svg("defs");
    const gradient = svg("linearGradient", { id: "chartGradient", x1: "0", x2: "0", y1: "0", y2: "1" });
    gradient.appendChild(svg("stop", { offset: "0%", "stop-color": metric.color, "stop-opacity": "0.22" }));
    gradient.appendChild(svg("stop", { offset: "100%", "stop-color": metric.color, "stop-opacity": "0" }));
    defs.appendChild(gradient);
    root.appendChild(defs);

    // Horizontal grid and y labels.
    for (let i = 0; i <= 4; i += 1) {
      const value = min + ((max - min) * i) / 4;
      const yy = y(value);
      root.appendChild(svg("line", { class: "chart-grid", x1: m.l, x2: W - m.r, y1: yy, y2: yy }));
      root.appendChild(
        svg("text", { class: "chart-axis-label", x: m.l - 9, y: yy + 3, "text-anchor": "end" }, metric.axis(value))
      );
    }

    // X labels.
    const xTicks = [0, Math.floor((history.length - 1) / 2), history.length - 1];
    [...new Set(xTicks)].forEach((index) => {
      root.appendChild(
        svg("text", { class: "chart-axis-label", x: x(index), y: H - 10, "text-anchor": index === 0 ? "start" : index === history.length - 1 ? "end" : "middle" }, `step ${history[index].step}`)
      );
    });

    const linePoints = values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(value).toFixed(2)}`).join(" ");
    const areaPoints = `${linePoints} L${x(values.length - 1).toFixed(2)},${(m.t + plotH).toFixed(2)} L${x(0).toFixed(2)},${(m.t + plotH).toFixed(2)} Z`;
    root.appendChild(svg("path", { class: "chart-area", d: areaPoints }));
    const line = svg("path", { class: "chart-line", d: linePoints });
    line.style.stroke = metric.color;
    root.appendChild(line);

    values.forEach((value, index) => {
      if (index === values.length - 1 || index % Math.max(1, Math.floor(values.length / 8)) === 0) {
        const dot = svg("circle", { class: "chart-dot", cx: x(index), cy: y(value), r: index === values.length - 1 ? 4 : 2.2 });
        dot.style.fill = metric.color;
        root.appendChild(dot);
      }
    });

    const hoverLine = svg("line", { class: "chart-hover-line", y1: m.t, y2: m.t + plotH, opacity: "0" });
    const hoverDot = svg("circle", { class: "chart-hover-dot", r: 3.5, opacity: "0" });
    hoverDot.style.fill = metric.color;
    root.appendChild(hoverLine);
    root.appendChild(hoverDot);
    const overlay = svg("rect", {
      x: m.l,
      y: m.t,
      width: plotW,
      height: plotH,
      fill: "transparent",
      style: "cursor: crosshair",
    });
    root.appendChild(overlay);

    overlay.addEventListener("mousemove", (event) => {
      const bounds = root.getBoundingClientRect();
      const rx = ((event.clientX - bounds.left) / bounds.width) * W;
      const ratio = Math.min(1, Math.max(0, (rx - m.l) / plotW));
      const index = Math.round(ratio * (history.length - 1));
      const yy = y(values[index]);
      hoverLine.setAttribute("x1", x(index));
      hoverLine.setAttribute("x2", x(index));
      hoverLine.setAttribute("opacity", "1");
      hoverDot.setAttribute("cx", x(index));
      hoverDot.setAttribute("cy", yy);
      hoverDot.setAttribute("opacity", "1");
      tooltipAt(
        event,
        `<strong>${esc(metric.label)}</strong><br>step ${history[index].step} · <b>${esc(metric.format(values[index]))}</b><br><span class="mono">${esc(state.result.meta.scenario)}</span>`
      );
    });
    overlay.addEventListener("mouseleave", () => {
      hoverLine.setAttribute("opacity", "0");
      hoverDot.setAttribute("opacity", "0");
      hideTooltip();
    });

    els.chart.appendChild(root);
    const latest = values[values.length - 1];
    els.chartCaption.textContent = `${metric.label} over time · latest ${metric.format(latest)}.`;
  }

  function populateFirmSelect() {
    const result = state.result;
    if (!result || !result.trees?.length) {
      els.firmSelect.innerHTML = "";
      els.treeMeta.textContent = "No live firms to inspect.";
      els.tree.innerHTML = '<div class="empty-state">No organisation selected yet.</div>';
      return;
    }
    const current = state.selectedFirm;
    els.firmSelect.innerHTML = result.trees
      .map((tree) => `<option value="${tree.id}">${esc(tree.name)} (${tree.headcount}, h${tree.height})</option>`)
      .join("");
    const exists = result.trees.some((tree) => String(tree.id) === String(current));
    els.firmSelect.value = exists ? String(current) : String(result.trees[0].id);
    state.selectedFirm = Number(els.firmSelect.value);
  }

  function renderSelectedFirm() {
    const result = state.result;
    if (!result || !result.trees?.length) return;
    const tree = result.trees.find((row) => String(row.id) === String(els.firmSelect.value)) || result.trees[0];
    state.selectedFirm = tree.id;
    els.treeMeta.innerHTML = [
      `<span><b>${tree.headcount}</b> employees</span>`,
      `<span><b>${tree.height}</b> levels</span>`,
      `<span><b>${pct(tree.manager_ratio)}</b> managers</span>`,
      `<span><b>${num(tree.output_per_worker, 1)}</b> output/head</span>`,
      `<span>span target <b>${tree.span_target}</b></span>`,
      tree.headcount > 55 ? "<span>scroll to explore →</span>" : "",
    ].join("");
    drawTree(tree);
  }

  function drawTree(tree) {
    const nodes = tree.nodes || [];
    if (!nodes.length) {
      els.tree.innerHTML = '<div class="empty-state">This firm has no employees.</div>';
      return;
    }
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const children = new Map(nodes.map((node) => [node.id, []]));
    nodes.forEach((node) => {
      if (node.manager_id !== null && node.manager_id !== undefined && children.has(node.manager_id)) {
        children.get(node.manager_id).push(node.id);
      }
    });
    children.forEach((list) => list.sort((a, b) => {
      const an = byId.get(a);
      const bn = byId.get(b);
      return (bn.reports - an.reports) || (an.id - bn.id);
    }));
    const rootId = tree.ceo_id ?? nodes.find((node) => node.manager_id === null)?.id ?? nodes[0].id;
    let leaf = 0;
    const positions = new Map();
    const visited = new Set();

    function walk(id) {
      if (visited.has(id)) return positions.get(id) ?? 0;
      visited.add(id);
      const kids = children.get(id) || [];
      let position;
      if (!kids.length) {
        position = leaf;
        leaf += 1;
      } else {
        const childPositions = kids.map((child) => walk(child));
        position = childPositions.reduce((sum, value) => sum + value, 0) / childPositions.length;
      }
      positions.set(id, position);
      return position;
    }

    walk(rootId);
    nodes.forEach((node) => {
      if (!positions.has(node.id)) {
        positions.set(node.id, leaf);
        leaf += 1;
      }
    });

    const leafCount = Math.max(leaf, 1);
    const maxDepth = Math.max(...nodes.map((node) => node.level || 0), 0);
    const rowGap = nodes.length > 60 ? 58 : 66;
    const width = Math.max(760, leafCount * 26 + 100);
    const height = 54 + (maxDepth + 1) * rowGap + 30;
    const padX = 50;
    const xFor = (position) => padX + ((position + 0.5) / leafCount) * (width - padX * 2);
    const yFor = (level) => 36 + (level || 0) * rowGap;

    const chart = svg("svg", {
      class: "tree-svg",
      viewBox: `0 0 ${width} ${height}`,
      preserveAspectRatio: "xMidYMin meet",
      role: "img",
      "aria-label": `Hierarchy of ${tree.name}`,
    });
    chart.setAttribute("width", width);
    chart.setAttribute("height", height);
    chart.style.width = `${width}px`;
    chart.style.height = `${height}px`;
    chart.style.minWidth = `${width}px`;

    // Links first.
    nodes.forEach((node) => {
      if (node.manager_id === null || node.manager_id === undefined) return;
      const parent = byId.get(node.manager_id);
      if (!parent) return;
      const x1 = xFor(positions.get(parent.id));
      const y1 = yFor(parent.level) + 9;
      const x2 = xFor(positions.get(node.id));
      const y2 = yFor(node.level) - 9;
      const mid = (y1 + y2) / 2;
      chart.appendChild(
        svg("path", {
          class: "tree-link",
          d: `M${x1.toFixed(2)},${y1.toFixed(2)} C${x1.toFixed(2)},${mid.toFixed(2)} ${x2.toFixed(2)},${mid.toFixed(2)} ${x2.toFixed(2)},${y2.toFixed(2)}`,
        })
      );
    });

    const showAllLabels = nodes.length <= 38;
    nodes.forEach((node) => {
      const cx = xFor(positions.get(node.id));
      const cy = yFor(node.level);
      const radius = 5 + Number(node.skill || 0) * 6;
      const group = svg("g", {
        class: "tree-node-group",
        "data-id": node.id,
        tabindex: "0",
        role: "button",
        "aria-label": `${node.name}, ${node.behavior}, level ${node.level}`,
      });
      group.appendChild(
        svg("circle", {
          class: `tree-node ${node.reports > 0 ? "manager" : ""}`,
          cx,
          cy,
          r: radius,
          fill: BEHAVIOR_COLORS[node.behavior] || "#94a4b8",
        })
      );
      if (node.reports > 0) {
        group.appendChild(svg("circle", { cx, cy, r: radius + 3.2, fill: "none", stroke: "#e8b45a", "stroke-opacity": "0.4", "stroke-width": "1" }));
      }
      if (showAllLabels || node.reports > 0 || node.id === rootId) {
        const label = node.name.length > 20 ? `${node.name.slice(0, 18)}…` : node.name;
        group.appendChild(
          svg(
            "text",
            {
              class: node.reports > 0 ? "node-label manager-label" : "node-label",
              x: cx,
              y: cy + radius + 11,
            },
            label
          )
        );
      }
      if (node.id === rootId) {
        group.appendChild(
          svg("text", { class: "node-ceo-label", x: cx, y: cy - radius - 10 }, "CEO")
        );
      }
      group.addEventListener("mouseenter", (event) => {
        tooltipAt(
          event,
          `<b>${esc(node.name)}</b><br>${esc(node.behavior)} · level ${node.level}<br>` +
            `<span class="mono">skill ${num(node.skill, 2)} · ambition ${num(node.ambition, 2)} · support ${num(node.support, 2)}</span><br>` +
            `<span class="mono">wage ${num(node.wage, 1)} · reports ${node.reports} · promotions ${node.promotions}</span>`
        );
      });
      group.addEventListener("mousemove", (event) => {
        tooltipAt(
          event,
          `<b>${esc(node.name)}</b><br>${esc(node.behavior)} · level ${node.level}<br>` +
            `<span class="mono">skill ${num(node.skill, 2)} · ambition ${num(node.ambition, 2)} · support ${num(node.support, 2)}</span><br>` +
            `<span class="mono">wage ${num(node.wage, 1)} · reports ${node.reports} · promotions ${node.promotions}</span>`
        );
      });
      group.addEventListener("mouseleave", hideTooltip);
      group.addEventListener("focus", (event) => {
        const rect = event.target.getBoundingClientRect();
        tooltipAt(
          { clientX: rect.left + rect.width / 2, clientY: rect.top },
          `<b>${esc(node.name)}</b><br>${esc(node.behavior)} · level ${node.level}<br><span class="mono">skill ${num(node.skill, 2)} · reports ${node.reports}</span>`
        );
      });
      group.addEventListener("blur", hideTooltip);
      chart.appendChild(group);
    });

    els.tree.innerHTML = "";
    els.tree.appendChild(chart);
    requestAnimationFrame(() => {
      els.tree.scrollLeft = Math.max(0, (els.tree.scrollWidth - els.tree.clientWidth) / 2);
    });
  }

  function renderEvents() {
    const events = state.result?.events || [];
    els.eventCount.textContent = `${events.length}`;
    if (!events.length) {
      els.events.innerHTML = '<div class="empty-state">No events in this run.</div>';
      return;
    }
    const shown = events.slice(-24).reverse();
    els.events.innerHTML = shown
      .map((event) => {
        const type = esc(event.type);
        let copy = "";
        if (event.type === "promotion") {
          copy = `<strong>${esc(event.agent)}</strong> promoted at <strong>${esc(event.firm)}</strong> · ${esc(event.reason || "merit")}`;
        } else if (event.type === "hire") {
          copy = `<strong>${esc(event.agent)}</strong> joined <strong>${esc(event.firm)}</strong> from ${esc(event.from || "the pool")}`;
        } else if (event.type === "exit") {
          copy = `<strong>${esc(event.firm)}</strong> exited · ${esc(event.reason || "closed")}`;
        } else if (event.type === "entry") {
          copy = `<strong>${esc(event.firm)}</strong> founded by ${esc(event.founder)} · span ${esc(event.strategy_span)}`;
        } else if (event.type === "layoff") {
          copy = `<strong>${esc(event.agent)}</strong> laid off from <strong>${esc(event.firm)}</strong>`;
        } else {
          copy = `${type} · ${esc(event.firm || "")}`;
        }
        return `<div class="event-item"><span class="event-step">s${esc(event.step)}</span><div class="event-copy"><span class="event-type ${type}">${type}</span>${copy}</div></div>`;
      })
      .join("");
  }

  // ------------------------------------------------------------------
  // Comparison and verdict
  // ------------------------------------------------------------------
  function renderVerdict(hypothesis, experiment) {
    if (!hypothesis) return;
    const verdict = hypothesis.verdict || "neutral";
    els.verdictBadge.className = `verdict-badge ${verdict}`;
    els.verdictBadge.textContent = verdict.replace("_", " ");
    els.verdictTitle.textContent = hypothesis.headline;
    const deltas = hypothesis.deltas;
    const conditions = hypothesis.conditions;
    const consistent = hypothesis.consistent_seed_directions;
    const nSeeds = hypothesis.paired_seeds.length;

    const deltaCards = [
      {
        label: "Height delta",
        value: signed(deltas.height, 2),
        unit: "levels",
        cls: deltas.height > 0 ? "good" : "bad",
      },
      {
        label: "Manager delta",
        value: signedPct(deltas.manager_ratio, 1),
        unit: "points",
        cls: deltas.manager_ratio > 0 ? "neutral" : "good",
      },
      {
        label: "Output delta",
        value: signed(deltas.productivity, 1),
        unit: "per worker",
        cls: deltas.productivity < 0 ? "bad" : "good",
      },
      {
        label: "Employment delta",
        value: signed(deltas.employment, 1),
        unit: "workers",
        cls: deltas.employment >= 0 ? "good" : "bad",
      },
      {
        label: "Survival delta",
        value: signedPct(deltas.survival, 1),
        unit: "points",
        cls: deltas.survival >= 0 ? "good" : "bad",
      },
      {
        label: "Margin delta",
        value: signedPct(deltas.profit_margin, 1),
        unit: "points",
        cls: deltas.profit_margin >= 0 ? "good" : "neutral",
      },
    ];

    els.verdictBody.innerHTML = `
      <p>${esc(hypothesis.note)}</p>
      <div class="delta-grid">
        ${deltaCards
          .map(
            (card) => `<div class="delta ${card.cls}"><span>${esc(card.label)}</span><strong>${esc(card.value)}</strong><small>${esc(card.unit)}</small></div>`
          )
          .join("")}
      </div>
      <div class="conditions">
        ${Object.entries(conditions)
          .map(
            ([key, passed]) =>
              `<div class="condition ${passed ? "pass" : "fail"}"><i>${passed ? "✓" : "×"}</i>${esc(CONDITION_LABELS[key] || key.replaceAll("_", " "))}</div>`
          )
          .join("")}
      </div>
      ${
        deltas.survival < 0
          ? `<p style="margin-top: 16px; font-size: 11px; color: var(--muted-dim);">
              Survival is <strong>lower</strong> in the baseline in this run — competition is eliminating
              some firms. The “still large” condition uses employment and average firm size, not survival.
            </p>`
          : ""
      }
      <p style="margin-top: 12px; font-size: 11px; color: var(--muted-dim);">
        Paired seeds: ${consistent.taller}/${nSeeds} taller · ${consistent.less_productive}/${nSeeds} less productive · ${consistent.not_smaller}/${nSeeds} not smaller.
        ${esc(experiment?.meta?.seeds?.length ? `Runs: ${experiment.meta.seeds.length} seed(s) per scenario, ${experiment.meta.steps} steps.` : "")}
      </p>
    `;
  }

  function renderComparison(experiment) {
    const aggregates = experiment.aggregates;
    const baseline = aggregates.baseline;
    const noLadder = aggregates.no_ladder;
    if (!baseline || !noLadder) return;
    els.compareSection.hidden = false;
    els.compareMeta.textContent = `${experiment.meta.seeds.length} seed${experiment.meta.seeds.length > 1 ? "s" : ""} · ${experiment.meta.steps} steps · ${experiment.meta.population} workers`;

    const rows = [
      ["Hierarchy height", baseline.weighted_height.mean, noLadder.weighted_height.mean, (v) => num(v, 2)],
      ["Manager ratio", baseline.weighted_manager_ratio.mean, noLadder.weighted_manager_ratio.mean, (v) => pct(v)],
      ["Output / worker", baseline.output_per_worker.mean, noLadder.output_per_worker.mean, (v) => num(v, 1)],
      ["Wage / worker", baseline.wage_per_worker.mean, noLadder.wage_per_worker.mean, (v) => num(v, 1)],
      ["Average firm size", baseline.avg_firm_size.mean, noLadder.avg_firm_size.mean, (v) => num(v, 1)],
      ["Employed", baseline.employed.mean, noLadder.employed.mean, (v) => num(v, 0)],
      ["Survival rate", baseline.survival_rate.mean, noLadder.survival_rate.mean, (v) => pct(v, 0)],
      ["Ladder discount", baseline.career_discount.mean, noLadder.career_discount.mean, (v) => pct(v)],
    ];
    els.compareTable.innerHTML = `
      <table class="compare-table">
        <thead><tr><th>Outcome</th><th>Baseline</th><th>No ladder</th><th>Delta</th></tr></thead>
        <tbody>
          ${rows
            .map(([label, b, n, format]) => {
              const delta = b - n;
              const formattedDelta =
                label.includes("ratio") || label.includes("rate") || label.includes("discount")
                  ? signedPct(delta, 1)
                  : signed(delta, 2);
              return `<tr class="${label === "Hierarchy height" ? "baseline-row" : ""}"><td>${esc(label)}</td><td>${esc(format(b))}</td><td>${esc(format(n))}</td><td>${esc(formattedDelta)}</td></tr>`;
            })
            .join("")}
        </tbody>
      </table>
    `;

    const bars = [
      ["Hierarchy height", baseline.weighted_height.mean, noLadder.weighted_height.mean, (v) => num(v, 2)],
      ["Output / worker", baseline.output_per_worker.mean, noLadder.output_per_worker.mean, (v) => num(v, 1)],
      ["Manager ratio", baseline.weighted_manager_ratio.mean, noLadder.weighted_manager_ratio.mean, (v) => pct(v)],
    ];
    els.compareBars.innerHTML = `
      <div class="bar-stack">
        ${bars
          .map(([label, b, n, format]) => {
            const max = Math.max(b, n, 0.001) * 1.12;
            return `<div class="bar-group">
              <span><span>${esc(label)}</span><b>${esc(format(b))} / ${esc(format(n))}</b></span>
              <div class="bar-pair">
                <div class="bar-track"><div class="bar-fill baseline" style="width:${(b / max) * 100}%"></div></div>
                <div class="bar-track"><div class="bar-fill noladder" style="width:${(n / max) * 100}%"></div></div>
              </div>
            </div>`;
          })
          .join("")}
      </div>
      <div class="bar-key"><span><i class="b"></i>baseline</span><span><i class="n"></i>no ladder</span></div>
    `;
  }

  // ------------------------------------------------------------------
  // Events
  // ------------------------------------------------------------------
  els.scenario.addEventListener("change", updateScenarioCopy);
  els.population.addEventListener("input", () => updateRangeOutput(els.population, els.populationOut));
  els.steps.addEventListener("input", () => updateRangeOutput(els.steps, els.stepsOut));
  els.runBtn.addEventListener("click", () => runSimulation());
  els.compareBtn.addEventListener("click", () => compareHypothesis());
  els.heroCompare.addEventListener("click", () => {
    document.querySelector("#simulator").scrollIntoView({ behavior: "smooth", block: "start" });
    compareHypothesis();
  });
  els.firmSelect.addEventListener("change", () => {
    state.selectedFirm = Number(els.firmSelect.value);
    renderSelectedFirm();
  });
  els.metricChips.addEventListener("click", (event) => {
    const button = event.target.closest(".metric-chip");
    if (!button) return;
    state.metric = button.dataset.metric;
    [...els.metricChips.querySelectorAll(".metric-chip")].forEach((chip) => {
      chip.classList.toggle("active", chip === button);
    });
    drawChart();
  });
  window.addEventListener("resize", debounce(drawChart, 180));

  // ------------------------------------------------------------------
  // Start
  // ------------------------------------------------------------------
  (async function init() {
    updateRangeOutput(els.population, els.populationOut);
    updateRangeOutput(els.steps, els.stepsOut);
    await loadScenarios();
    await runSimulation({ initial: true });
    if (new URLSearchParams(window.location.search).get("compare") === "1") {
      await compareHypothesis({ silent: true });
    }
  })();
})();
