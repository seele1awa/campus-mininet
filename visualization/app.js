const model = {
  coreSwitch: { id: "s_core", label: "s_core", role: "core-switch", ip: "trunk", x: 580, y: 300 },
  router: { id: "r_core", label: "核心路由", role: "router", ip: "VLAN 子接口网关", x: 580, y: 378 },
  areas: [
    {
      id: "student",
      label: "学生宿舍",
      subnet: "10.10.10.0/24",
      gateway: "10.10.10.1",
      vlan: 10,
      switch: { id: "s_stu", label: "s_stu", x: 210, y: 180 },
      hosts: [
        { id: "stu1", label: "stu1", ip: "10.10.10.11", x: 110, y: 95 },
        { id: "stu2", label: "stu2", ip: "10.10.10.12", x: 210, y: 75 },
        { id: "stu3", label: "stu3", ip: "10.10.10.13", x: 310, y: 95 },
      ],
      box: { x: 45, y: 42, width: 330, height: 190 },
    },
    {
      id: "teaching",
      label: "教学楼",
      subnet: "10.10.20.0/24",
      gateway: "10.10.20.1",
      vlan: 20,
      switch: { id: "s_teach", label: "s_teach", x: 580, y: 155 },
      hosts: [
        { id: "teach1", label: "teach1", ip: "10.10.20.11", x: 505, y: 72 },
        { id: "teach2", label: "teach2", ip: "10.10.20.12", x: 655, y: 72 },
      ],
      box: { x: 430, y: 42, width: 300, height: 180 },
    },
    {
      id: "library",
      label: "图书馆",
      subnet: "10.10.30.0/24",
      gateway: "10.10.30.1",
      vlan: 30,
      switch: { id: "s_lib", label: "s_lib", x: 940, y: 180 },
      hosts: [
        { id: "lib1", label: "lib1", ip: "10.10.30.11", x: 860, y: 95 },
        { id: "lib2", label: "lib2", ip: "10.10.30.12", x: 1020, y: 95 },
      ],
      box: { x: 795, y: 42, width: 300, height: 190 },
    },
    {
      id: "office",
      label: "办公楼",
      subnet: "10.10.40.0/24",
      gateway: "10.10.40.1",
      vlan: 40,
      switch: { id: "s_office", label: "s_office", x: 190, y: 520 },
      hosts: [
        { id: "office1", label: "office1", ip: "10.10.40.11", x: 105, y: 610 },
        { id: "office2", label: "office2", ip: "10.10.40.12", x: 275, y: 610 },
      ],
      box: { x: 45, y: 470, width: 300, height: 185 },
    },
    {
      id: "hr",
      label: "人事处",
      subnet: "10.10.50.0/24",
      gateway: "10.10.50.1",
      vlan: 50,
      switch: { id: "s_hr", label: "s_hr", x: 455, y: 548 },
      hosts: [{ id: "hr1", label: "hr1", ip: "10.10.50.11", x: 455, y: 625 }],
      box: { x: 375, y: 492, width: 160, height: 170 },
    },
    {
      id: "finance",
      label: "财务处",
      subnet: "10.10.60.0/24",
      gateway: "10.10.60.1",
      vlan: 60,
      switch: { id: "s_fin", label: "s_fin", x: 705, y: 548 },
      hosts: [{ id: "fin1", label: "fin1", ip: "10.10.60.11", x: 705, y: 625 }],
      box: { x: 625, y: 492, width: 160, height: 170 },
    },
    {
      id: "server",
      label: "服务器区",
      subnet: "10.10.100.0/24",
      gateway: "10.10.100.1",
      vlan: 100,
      switch: { id: "s_srv", label: "s_srv", x: 970, y: 520 },
      hosts: [
        { id: "web", label: "web", ip: "10.10.100.10", role: "server", service: "HTTP:80", x: 890, y: 610 },
        { id: "ftp", label: "ftp", ip: "10.10.100.20", role: "server", service: "FTP:21", x: 1050, y: 610 },
      ],
      box: { x: 825, y: 470, width: 290, height: 185 },
    },
    {
      id: "external",
      label: "外部模拟区",
      subnet: "203.0.113.0/24",
      gateway: "203.0.113.1",
      vlan: 200,
      switch: { id: "s_ext", label: "s_ext", x: 580, y: 515 },
      hosts: [{ id: "attacker1", label: "attacker1", ip: "203.0.113.100", x: 580, y: 620 }],
      hiddenBox: true,
    },
  ],
};

const fallbackPolicies = [
  { title: "普通区域隔离", body: "学生宿舍、教学楼、图书馆不能访问人事处和财务处。" },
  { title: "办公业务放行", body: "办公楼允许访问人事处和财务处。" },
  { title: "服务区共享", body: "内网用户允许访问 Web/FTP 服务器。" },
  { title: "外部访问阻断", body: "外部模拟区不能进入校园内网。" },
];

const fallbackTemplates = [
  { id: "courseware", label: "课件共享通知", text: "教学楼发送课件共享通知：请同步今日计算机网络实验资料。" },
  { id: "office", label: "办公审批消息", text: "办公楼发送行政审批消息：请确认本周会议室使用申请。" },
  { id: "finance", label: "财务预算请求", text: "财务处预算请求：请提交本月设备采购费用明细。" },
  { id: "custom", label: "自定义消息", text: "请输入自定义消息。" },
];

const quickScenarios = [
  { label: "宿舍内部 ping", action: "ping", source: "stu1", target: "stu2" },
  { label: "宿舍到教学楼 ping", action: "ping", source: "stu1", target: "teach1" },
  { label: "学生访问 Web", action: "web", source: "stu1", target: "web" },
  { label: "学生下载 FTP", action: "ftp", source: "stu1", target: "ftp" },
  { label: "学生访问人事处", action: "ping", source: "stu1", target: "hr1" },
  { label: "办公楼发给财务处", action: "message", source: "office1", target: "fin1", message: "办公楼发送审批数据：请财务处确认项目经费。" },
  { label: "学生到服务器性能", action: "perf", source: "stu1", target: "web" },
  { label: "服务器区内部高速", action: "perf", source: "web", target: "ftp" },
];

const svg = document.getElementById("topologySvg");
const backendBadge = document.getElementById("backendBadge");
const topologyBadge = document.getElementById("topologyBadge");
const pathSummary = document.getElementById("pathSummary");
const actionSource = document.getElementById("actionSource");
const actionTarget = document.getElementById("actionTarget");
const actionType = document.getElementById("actionType");
const messageSource = document.getElementById("messageSource");
const messageTarget = document.getElementById("messageTarget");
const messageTemplate = document.getElementById("messageTemplate");
const messageText = document.getElementById("messageText");
const resultTitle = document.getElementById("resultTitle");
const resultReason = document.getElementById("resultReason");
const terminalOutput = document.getElementById("terminalOutput");
const nodeDetails = document.getElementById("nodeDetails");
const eventLog = document.getElementById("eventLog");
const auditLog = document.getElementById("auditLog");
const auditSummary = document.getElementById("auditSummary");
const policyGrid = document.getElementById("policyGrid");
const scenarioList = document.getElementById("scenarioList");

const nodes = new Map();
const links = [];
let selectedNode = "r_core";
let backendOnline = false;
let topologyRunning = false;
let templates = fallbackTemplates;
let policies = fallbackPolicies;
let templateSignature = "";

function addNode(node, areaId, role) {
  nodes.set(node.id, { ...node, areaId, role: role || node.role || "host" });
}

function prepareModel() {
  addNode(model.router, "core", "router");
  addNode(model.coreSwitch, "core", "core-switch");
  links.push({ a: model.coreSwitch.id, b: model.router.id, id: `${model.coreSwitch.id}-${model.router.id}`, mode: "trunk" });
  model.areas.forEach((area) => {
    addNode({ ...area.switch, vlan: area.vlan, portMode: "trunk" }, area.id, "switch");
    links.push({ a: area.switch.id, b: model.coreSwitch.id, id: `${area.switch.id}-${model.coreSwitch.id}`, mode: "trunk" });
    area.hosts.forEach((host) => {
      addNode({ ...host, vlan: area.vlan, portMode: "access" }, area.id, host.role || "host");
      links.push({ a: host.id, b: area.switch.id, id: `${host.id}-${area.switch.id}`, mode: "access" });
    });
  });
}

function mergeTopology(status) {
  if (!status?.areas) return;
  status.areas.forEach((nextArea) => {
    const area = model.areas.find((item) => item.id === nextArea.id);
    if (!area) return;
    area.vlan = nextArea.vlan ?? area.vlan;
    area.gateway = nextArea.gateway || area.gateway;
    area.subnet = nextArea.subnet || area.subnet;
    nextArea.hosts?.forEach((nextHost) => {
      const host = area.hosts.find((item) => item.id === nextHost.id);
      if (host) Object.assign(host, nextHost);
      const node = nodes.get(nextHost.id);
      if (node) Object.assign(node, nextHost);
    });
    const switchNode = nodes.get(area.switch.id);
    if (switchNode) Object.assign(switchNode, { vlan: area.vlan, portMode: "trunk" });
  });
}

function areaForNode(id) {
  return model.areas.find((area) => area.id === nodes.get(id)?.areaId);
}

function hostNodes() {
  return [...nodes.values()].filter((node) => node.role === "host" || node.role === "server");
}

function setHostOptions() {
  const options = hostNodes()
    .map((node) => `<option value="${node.id}">${node.label} - ${node.ip}</option>`)
    .join("");
  [actionSource, actionTarget, messageSource, messageTarget].forEach((select) => {
    select.innerHTML = options;
  });
  actionSource.value = "stu1";
  actionTarget.value = "web";
  messageSource.value = "office1";
  messageTarget.value = "fin1";
}

function setTemplateOptions() {
  const previousValue = messageTemplate.value;
  const previousText = messageText.value;
  messageTemplate.innerHTML = templates.map((item) => `<option value="${item.id}">${item.label}</option>`).join("");
  messageTemplate.value = templates.some((item) => item.id === previousValue) ? previousValue : templates[0]?.id || "custom";
  if (previousText && messageTemplate.value === previousValue) {
    messageText.value = previousText;
  } else {
    setTemplateText();
  }
}

function setTemplateText() {
  const template = templates.find((item) => item.id === messageTemplate.value);
  if (template && template.id !== "custom") {
    messageText.value = template.text;
  } else if (!messageText.value || messageText.value === "请输入自定义消息。") {
    messageText.value = "请输入自定义消息。";
  }
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function renderTopology() {
  svg.innerHTML = "";

  model.areas.forEach((area) => {
    if (area.hiddenBox) return;
    svg.appendChild(svgEl("rect", {
      class: "area-box",
      x: area.box.x,
      y: area.box.y,
      width: area.box.width,
      height: area.box.height,
      rx: 8,
    }));
    const label = svgEl("text", {
      class: "area-label",
      x: area.box.x + area.box.width / 2,
      y: area.box.y + 28,
    });
    label.textContent = `${area.label} · VLAN ${area.vlan}`;
    svg.appendChild(label);
  });

  links.forEach((link) => {
    const a = nodes.get(link.a);
    const b = nodes.get(link.b);
    svg.appendChild(svgEl("line", {
      class: "svg-link",
      id: `link-${link.id}`,
      x1: a.x,
      y1: a.y,
      x2: b.x,
      y2: b.y,
    }));
  });

  [...nodes.values()].forEach((node) => {
    const group = svgEl("g", {
      class: `node-group ${node.id === selectedNode ? "selected" : ""}`,
      id: `node-${node.id}`,
      tabindex: "0",
    });
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") selectNode(node.id);
    });

    const color = node.role === "router" ? "#0f766e" : node.role === "core-switch" ? "#1d4ed8" : node.role === "switch" ? "#2563eb" : node.role === "server" ? "#7c3aed" : "#b45309";
    const shape = svgEl(node.role === "switch" || node.role === "core-switch" ? "rect" : "circle", node.role === "switch" || node.role === "core-switch"
      ? { class: "node-shape", x: node.x - 31, y: node.y - 22, width: 62, height: 44, rx: 8, fill: color }
      : { class: "node-shape", cx: node.x, cy: node.y, r: node.role === "router" ? 40 : 28, fill: color });
    group.appendChild(shape);

    const label = svgEl("text", { class: "node-label", x: node.x, y: node.y + 5 });
    label.textContent = node.label;
    group.appendChild(label);

    const sub = svgEl("text", { class: "node-sub", x: node.x, y: node.y + (node.role === "switch" || node.role === "core-switch" ? 40 : 46) });
    sub.textContent = node.role === "router" ? "L3 VLAN GW" : node.role === "core-switch" ? "trunk" : node.role === "switch" ? `VLAN ${node.vlan}` : node.ip;
    group.appendChild(sub);
    svg.appendChild(group);

    if (node.areaId === "external") {
      const area = areaForNode(node.id);
      const areaLabel = svgEl("text", { class: "area-label", x: node.x, y: node.y - 70 });
      areaLabel.textContent = area.label;
      svg.appendChild(areaLabel);
    }
  });
}

function selectNode(id) {
  selectedNode = id;
  renderTopology();
  renderNodeDetails(id);
}

function renderNodeDetails(id) {
  const node = nodes.get(id);
  const area = areaForNode(id);
  const details = [
    ["节点", node.label],
    ["类型", node.role === "router" ? "核心路由器" : node.role === "core-switch" ? "核心交换机" : node.role === "switch" ? "接入交换机" : node.role === "server" ? "服务器" : "终端主机"],
    ["区域", area ? area.label : "核心层"],
    ["地址", node.ip || area?.gateway || "多接口"],
  ];
  if (area) {
    details.push(["VLAN", area.vlan], ["端口模式", node.portMode || (node.role === "switch" ? "trunk" : "access")], ["网段", area.subnet], ["网关", area.gateway]);
  } else if (node.role === "core-switch") {
    details.push(["端口模式", "trunk"], ["承载 VLAN", model.areas.map((item) => item.vlan).join(", ")]);
  }
  if (node.service) {
    details.push(["服务", node.service]);
  }
  nodeDetails.innerHTML = details.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join("");
}

function pathBetween(source, target) {
  const sourceArea = areaForNode(source);
  const targetArea = areaForNode(target);
  if (!sourceArea || !targetArea) return [];
  if (sourceArea.id === targetArea.id) {
    return [source, sourceArea.switch.id, target];
  }
  return [source, sourceArea.switch.id, "s_core", "r_core", "s_core", targetArea.switch.id, target];
}

function clearLinkStates() {
  document.querySelectorAll(".svg-link").forEach((link) => {
    link.classList.remove("active", "denied");
  });
}

function linkIdFor(a, b) {
  return `link-${a}-${b}`;
}

function markPath(path, ok) {
  clearLinkStates();
  path.forEach((id) => {
    const node = document.getElementById(`node-${id}`);
    if (node) node.classList.add("selected");
  });
  for (let index = 0; index < path.length - 1; index += 1) {
    const a = path[index];
    const b = path[index + 1];
    const link = document.getElementById(linkIdFor(a, b)) || document.getElementById(linkIdFor(b, a));
    if (link) {
      link.classList.add(ok ? "active" : "denied");
    }
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false && data.error) {
    throw new Error(data.error || `请求失败：${response.status}`);
  }
  return data;
}

function setBusy(isBusy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function updateBadges() {
  backendBadge.textContent = backendOnline ? "后端已连接" : "后端未连接";
  backendBadge.className = `badge ${backendOnline ? "ok" : "warn"}`;
  topologyBadge.textContent = topologyRunning ? "真实拓扑运行中" : "拓扑未启动";
  topologyBadge.className = `badge ${topologyRunning ? "ok" : "idle"}`;
}

function renderPolicies() {
  policyGrid.innerHTML = policies
    .map((policy) => `<article class="policy-card"><strong>${policy.title}</strong><p>${policy.body}</p></article>`)
    .join("");
}

function renderEvents(events = []) {
  if (!events.length) {
    eventLog.innerHTML = '<div class="event-item"><strong>--</strong>暂无后端事件。</div>';
    return;
  }
  eventLog.innerHTML = events
    .slice()
    .reverse()
    .map((event) => `<div class="event-item ${event.ok ? "ok" : "fail"}"><strong>${event.time}</strong>${event.message}</div>`)
    .join("");
}

function levelText(level) {
  if (level === "high") return "高风险";
  if (level === "blocked") return "阻断";
  return "正常";
}

function renderAudit(audit = [], summary = {}) {
  auditSummary.innerHTML = [
    `<span>总计 ${summary.total || audit.length || 0}</span>`,
    `<span>高风险 ${summary.high || 0}</span>`,
    `<span>阻断 ${summary.blocked || 0}</span>`,
  ].join("");

  if (!audit.length) {
    auditLog.innerHTML = '<div class="audit-item normal"><strong>暂无审计记录</strong><p>执行真实测试后会出现访问审计。</p></div>';
    return;
  }

  auditLog.innerHTML = audit
    .slice()
    .reverse()
    .map((item) => `
      <article class="audit-item ${item.level}">
        <div><strong>${item.time}</strong><span>${levelText(item.level)}</span></div>
        <p>${item.source} (${item.sourceArea}) -> ${item.target} (${item.targetArea}) · ${item.action} · ${item.ok ? "成功" : "失败"}</p>
        <small>${item.reason}</small>
      </article>
    `)
    .join("");
}

async function refreshStatus() {
  try {
    const status = await api("/api/status");
    backendOnline = true;
    topologyRunning = Boolean(status.running);
    mergeTopology(status);
    policies = status.policies || policies;
    const nextTemplates = status.messageTemplates || templates;
    const nextSignature = JSON.stringify(nextTemplates.map((item) => [item.id, item.label, item.text]));
    if (nextSignature !== templateSignature) {
      templates = nextTemplates;
      templateSignature = nextSignature;
      setTemplateOptions();
    }
    renderPolicies();
    renderEvents(status.events || []);
    renderAudit(status.audit || [], status.auditSummary || {});
    updateBadges();
  } catch (error) {
    backendOnline = false;
    topologyRunning = false;
    updateBadges();
    renderEvents([]);
    renderAudit([], {});
  }
}

function commandOutput(result) {
  const parts = [
    `操作: ${result.action || "unknown"}`,
    `源主机: ${result.source || "-"}`,
    `目标主机: ${result.target || "-"} ${result.targetIp ? `(${result.targetIp})` : ""}`,
    `退出码: ${result.rc ?? "-"}`,
    `命令: ${result.command || "-"}`,
  ];
  if (result.auditLevel) {
    parts.push(`审计级别: ${levelText(result.auditLevel)}`, `审计原因: ${result.auditReason || "-"}`);
  }
  if (result.action === "perf") {
    parts.push(`吞吐量: ${result.mbps ?? "-"} Mbps`, `性能预期: ${result.expectedProfile || "-"}`);
  }
  parts.push("", "输出:", result.output || "(无输出)");
  if (result.received) {
    parts.push("", "目标主机接收记录:", JSON.stringify(result.received, null, 2));
  }
  if (result.rawOutput && result.action === "perf") {
    parts.push("", "iperf3 原始 JSON:", result.rawOutput);
  }
  return parts.join("\n");
}

function showResult(result) {
  const ok = Boolean(result.ok);
  resultTitle.textContent = ok ? "真实执行成功" : "真实执行失败";
  resultTitle.className = `result-title ${ok ? "allowed" : "denied"}`;
  if (result.action === "message") {
    const payload = result.received?.payload;
    resultReason.textContent = ok
      ? `${result.target} 实际收到来自 ${result.source} 的消息：“${payload?.message || result.message}”。`
      : "消息没有到达目标主机，可能被 ACL 阻断或目标服务不可达。";
  } else if (result.action === "perf") {
    resultReason.textContent = ok
      ? `iperf3 实测吞吐量 ${result.mbps} Mbps。${result.expectedProfile}`
      : "iperf3 性能测试失败，可能目标不可达、ACL 阻断或 iperf3 未安装。";
  } else if (result.action === "web") {
    resultReason.textContent = ok ? "Web 页面由 Mininet 中的 web 主机真实返回。" : "HTTP 访问失败，可能目标不是 Web 服务器或路径被阻断。";
  } else if (result.action === "ftp") {
    resultReason.textContent = ok ? "FTP 文件由 Mininet 中的 ftp 主机真实返回。" : "FTP 下载失败，可能目标不是 FTP 服务器或路径被阻断。";
  } else {
    resultReason.textContent = ok ? "ICMP 报文在真实 Mininet 拓扑中到达目标。" : "ICMP 报文未到达目标，ACL 或链路策略生效。";
  }
  terminalOutput.textContent = commandOutput(result);
  selectNode(result.target);
  const path = pathBetween(result.source, result.target);
  markPath(path, ok);
  pathSummary.textContent = `${nodes.get(result.source)?.label || result.source} -> ${nodes.get(result.target)?.label || result.target}: ${path.map((id) => nodes.get(id)?.label || id).join(" -> ")}`;
}

async function runAction(action, source, target, message) {
  setBusy(true);
  try {
    const result = await api("/api/run", {
      method: "POST",
      body: JSON.stringify({ action, source, target, message }),
    });
    showResult(result);
    await refreshStatus();
  } catch (error) {
    resultTitle.textContent = "执行失败";
    resultTitle.className = "result-title denied";
    resultReason.textContent = error.message;
    terminalOutput.textContent = error.stack || error.message;
  } finally {
    setBusy(false);
  }
}

async function startTopology() {
  setBusy(true);
  try {
    const result = await api("/api/start", { method: "POST", body: "{}" });
    terminalOutput.textContent = result.message;
    await refreshStatus();
  } catch (error) {
    terminalOutput.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function stopTopology() {
  setBusy(true);
  try {
    const result = await api("/api/stop", { method: "POST", body: "{}" });
    terminalOutput.textContent = result.message;
    clearLinkStates();
    await refreshStatus();
  } catch (error) {
    terminalOutput.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function runTests() {
  setBusy(true);
  try {
    const result = await api("/api/tests", { method: "POST", body: "{}" });
    resultTitle.textContent = result.ok ? "自动测试通过" : "自动测试存在失败";
    resultTitle.className = `result-title ${result.ok ? "allowed" : "denied"}`;
    resultReason.textContent = `${result.results.filter((item) => item.passed).length}/${result.results.length} 项通过。`;
    terminalOutput.textContent = result.results
      .map((item) => `[${item.passed ? "PASS" : "FAIL"}] ${item.title} | 预期 ${item.expectOk ? "成功" : "失败"} | 实际 ${item.ok ? "成功" : "失败"}`)
      .join("\n");
    await refreshStatus();
  } catch (error) {
    terminalOutput.textContent = error.stack || error.message;
  } finally {
    setBusy(false);
  }
}

function renderScenarios() {
  scenarioList.innerHTML = "";
  quickScenarios.forEach((scenario) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = scenario.label;
    button.addEventListener("click", () => runAction(scenario.action, scenario.source, scenario.target, scenario.message || messageText.value));
    scenarioList.appendChild(button);
  });
}

function bindEvents() {
  document.getElementById("startTopology").addEventListener("click", startTopology);
  document.getElementById("stopTopology").addEventListener("click", stopTopology);
  document.getElementById("runAction").addEventListener("click", () => runAction(actionType.value, actionSource.value, actionTarget.value));
  document.getElementById("sendMessage").addEventListener("click", () => runAction("message", messageSource.value, messageTarget.value, messageText.value));
  document.getElementById("runTests").addEventListener("click", runTests);
  messageTemplate.addEventListener("change", setTemplateText);
}

async function init() {
  prepareModel();
  setHostOptions();
  setTemplateOptions();
  renderTopology();
  renderPolicies();
  renderScenarios();
  renderNodeDetails(selectedNode);
  bindEvents();
  await refreshStatus();
  setInterval(refreshStatus, 4000);
}

init();
