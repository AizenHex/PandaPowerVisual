// AutoCAD-Style Interactive Grid Simulator Client
const NODE_SIZE = {
  source: { w: 150, h: 112 },
  bus: { w: 150, h: 112 },
  trafo: { w: 190, h: 112 },
  load: { w: 165, h: 92 },
  gen: { w: 150, h: 92 },
  shunt: { w: 165, h: 92 },
};

const LABEL_BY_KIND = {
  source: "Slack Bus",
  bus: "Busbar",
  trafo: "Transformer",
  load: "Beban",
  gen: "Generator",
  shunt: "Shunt Kapasitor",
};

const DEFAULT_NEXT_ID = {
  source: 1,
  bus: 1,
  load: 1,
  gen: 1,
  shunt: 1,
  trafo: 1,
  line: 1,
};

function normalizeNextId(nextId = {}) {
  return { ...DEFAULT_NEXT_ID, ...nextId };
}

const state = {
  nodes: {},
  links: {},
  zoom: 1.0,
  pan: { x: 50, y: 50 },
  selectedId: null,
  selectedType: null, // 'node' or 'link'
  
  // Interaction states
  isPanning: false,
  startPan: { x: 0, y: 0 },
  draggedNode: null,
  dragStarted: false,
  dragOffset: { x: 0, y: 0 },
  connectingPin: null, // { nodeId, pinName, x, y }
  
  // History Undo/Redo stacks
  undoStack: [],
  redoStack: [],
  
  // Simulation & validation results
  hasResults: false,
  results: { nodes: {}, links: {} },
  validationErrors: [],
  validationWarnings: [],
  
  // Auto-increment IDs
  nextId: normalizeNextId(),
};

// DOM Elements
const svg = document.getElementById("sldSvg");
const contentGroup = document.getElementById("canvasContent");
const nodesGroup = document.getElementById("nodesGroup");
const linksGroup = document.getElementById("linksGroup");
const viewport = document.getElementById("canvasViewport");
const zoomReadout = document.getElementById("zoomReadout");
const statusPill = document.getElementById("statusPill");
const summaryGrid = document.getElementById("summaryGrid");
const validationBox = document.getElementById("validationBox");
const propertiesBody = document.getElementById("propertiesBody");
const selectedKind = document.getElementById("selectedKind");
const resultRows = document.getElementById("resultRows");
const resultState = document.getElementById("resultState");
const canvasMeta = document.getElementById("canvasMeta");
const tempConnectionLine = document.getElementById("tempConnectionLine");

// Initialize History Snapshots
function pushHistory() {
  const snapshot = JSON.stringify({
    nodes: state.nodes,
    links: state.links,
    nextId: state.nextId,
  });
  state.undoStack.push(snapshot);
  if (state.undoStack.length > 50) state.undoStack.shift();
  state.redoStack = []; // Clear redo stack on new action
}

function undo() {
  if (state.undoStack.length === 0) {
    showStatus("Tidak ada aksi untuk Undo", "warn");
    return;
  }
  const current = JSON.stringify({
    nodes: state.nodes,
    links: state.links,
    nextId: state.nextId,
  });
  state.redoStack.push(current);
  
  const raw = state.undoStack.pop();
  const data = JSON.parse(raw);
  state.nodes = data.nodes;
  state.links = data.links;
  state.nextId = normalizeNextId(data.nextId);
  state.selectedId = null;
  state.selectedType = null;
  state.hasResults = false;
  
  showStatus("Undo berhasil", "ok");
  renderAll();
}

function redo() {
  if (state.redoStack.length === 0) {
    showStatus("Tidak ada aksi untuk Redo", "warn");
    return;
  }
  const raw = state.redoStack.pop();
  state.undoStack.push(JSON.stringify({
    nodes: state.nodes,
    links: state.links,
    nextId: state.nextId,
  }));
  
  const data = JSON.parse(raw);
  state.nodes = data.nodes;
  state.links = data.links;
  state.nextId = normalizeNextId(data.nextId);
  state.selectedId = null;
  state.selectedType = null;
  state.hasResults = false;
  
  showStatus("Redo berhasil", "ok");
  renderAll();
}

// Helper to set visual status pill
function showStatus(text, tone = "ok") {
  statusPill.textContent = text;
  statusPill.className = `status-pill ${tone}`;
}

// -------------------------------------------------------------
// Component Pin Definitions (Ports for connections)
// -------------------------------------------------------------
function getPins(nodeData) {
  const { id, kind, x, y } = nodeData;
  const size = NODE_SIZE[kind];
  
  if (kind === "bus") {
    // A Bus has multiple connection points on its top and bottom sides
    return [
      { name: "in", label: "IN", cx: x + size.w / 4, cy: y, dir: { x: 0, y: -1 } },
      { name: "in_2", label: "IN2", cx: x + (size.w * 3) / 4, cy: y, dir: { x: 0, y: -1 } },
      { name: "out", label: "OUT", cx: x + size.w / 4, cy: y + size.h, dir: { x: 0, y: 1 } },
      { name: "out_2", label: "OUT2", cx: x + (size.w * 3) / 4, cy: y + size.h, dir: { x: 0, y: 1 } }
    ];
  }
  if (kind === "source") {
    return [
      { name: "out", label: "OUT", cx: x + size.w, cy: y + size.h / 2, dir: { x: 1, y: 0 } }
    ];
  }
  if (kind === "trafo") {
    return [
      { name: "hv", label: "HV", cx: x, cy: y + size.h / 2, dir: { x: -1, y: 0 } },
      { name: "lv", label: "LV", cx: x + size.w, cy: y + size.h / 2, dir: { x: 1, y: 0 } }
    ];
  }
  if (kind === "load") {
    return [
      { name: "pin", label: "IN", cx: x + size.w / 2, cy: y, dir: { x: 0, y: -1 } }
    ];
  }
  if (kind === "gen") {
    return [
      { name: "pin", label: "OUT", cx: x + size.w / 2, cy: y + size.h, dir: { x: 0, y: 1 } }
    ];
  }
  if (kind === "shunt") {
    return [
      { name: "pin", label: "IN", cx: x + size.w / 2, cy: y, dir: { x: 0, y: -1 } }
    ];
  }
  return [];
}

// Find closest pin on a node to a given coordinates
function getClosestPin(nodeData, x, y) {
  const pins = getPins(nodeData);
  let closest = null;
  let minDist = Infinity;
  pins.forEach(pin => {
    const dist = Math.hypot(pin.cx - x, pin.cy - y);
    if (dist < minDist) {
      minDist = dist;
      closest = pin;
    }
  });
  return closest;
}

// Get specific pin coordinates by name
function getPinCoords(nodeId, pinName) {
  const node = state.nodes[nodeId];
  if (!node) return { x: 0, y: 0, dir: { x: 0, y: 0 } };
  const pins = getPins(node);
  const pin = pins.find(p => p.name === pinName) || pins[0];
  return { x: pin.cx, y: pin.cy, dir: pin.dir };
}

// -------------------------------------------------------------
// AutoCAD-style Pan & Zoom Handlers
// -------------------------------------------------------------
function updateViewportTransform() {
  contentGroup.setAttribute("transform", `translate(${state.pan.x}, ${state.pan.y}) scale(${state.zoom})`);
  
  // Sync background grid position & zoom
  const gridBackground = document.getElementById("gridBackground");
  const majorGrid = document.getElementById("majorGrid");
  const minorGrid = document.getElementById("minorGrid");
  
  const zoomFactor = state.zoom;
  minorGrid.setAttribute("width", 15 * zoomFactor);
  minorGrid.setAttribute("height", 15 * zoomFactor);
  minorGrid.querySelector("path").setAttribute("d", `M ${15 * zoomFactor} 0 L 0 0 0 ${15 * zoomFactor}`);
  
  majorGrid.setAttribute("width", 75 * zoomFactor);
  majorGrid.setAttribute("height", 75 * zoomFactor);
  majorGrid.querySelector("path").setAttribute("d", `M ${75 * zoomFactor} 0 L 0 0 0 ${75 * zoomFactor}`);
  
  // Offset grid to align with pan
  gridBackground.setAttribute("x", state.pan.x % (75 * zoomFactor));
  gridBackground.setAttribute("y", state.pan.y % (75 * zoomFactor));
  
  zoomReadout.textContent = `${Math.round(state.zoom * 100)}%`;
}

function setZoom(newZoom) {
  state.zoom = Math.min(4.0, Math.max(0.2, newZoom));
  updateViewportTransform();
}

function zoomIn() {
  setZoom(state.zoom * 1.25);
}

function zoomOut() {
  setZoom(state.zoom / 1.25);
}

function zoomReset() {
  state.zoom = 1.0;
  updateViewportTransform();
  showStatus("Zoom: 100%", "ok");
}

function handleZoom(event) {
  event.preventDefault();
  const zoomFactor = 1.15;
  const oldZoom = state.zoom;
  
  // Calculate zoom scale change
  let newZoom = oldZoom;
  if (event.deltaY < 0) {
    newZoom = Math.min(4.0, oldZoom * zoomFactor);
  } else {
    newZoom = Math.max(0.2, oldZoom / zoomFactor);
  }
  
  // Zoom centered on mouse pointer position
  const rect = viewport.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  
  // Canvas coordinates under mouse cursor before zoom change
  const canvasX = (mouseX - state.pan.x) / oldZoom;
  const canvasY = (mouseY - state.pan.y) / oldZoom;
  
  state.zoom = newZoom;
  state.pan.x = mouseX - canvasX * newZoom;
  state.pan.y = mouseY - canvasY * newZoom;
  
  updateViewportTransform();
}

function handleMouseDown(event) {
  const rect = viewport.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  
  // Determine coordinate on canvas
  const canvasX = (mouseX - state.pan.x) / state.zoom;
  const canvasY = (mouseY - state.pan.y) / state.zoom;
  
  // Check if click is on a pin (start connection)
  const pinTarget = event.target.closest(".sld-pin");
  if (pinTarget) {
    event.stopPropagation();
    const nodeId = pinTarget.dataset.nodeId;
    const pinName = pinTarget.dataset.pinName;
    const coords = getPinCoords(nodeId, pinName);
    state.connectingPin = { nodeId, pinName, x: coords.x, y: coords.y };
    tempConnectionLine.style.display = "block";
    tempConnectionLine.setAttribute("d", `M ${coords.x} ${coords.y} L ${coords.x} ${coords.y}`);
    return;
  }
  
  // Check if click is on a node (select/drag)
  const nodeTarget = event.target.closest(".sld-node-group");
  if (nodeTarget) {
    event.stopPropagation();
    const nodeId = nodeTarget.dataset.nodeId;
    selectElement(nodeId, "node");
    
    const node = state.nodes[nodeId];
    state.draggedNode = nodeId;
    state.dragStarted = false;
    state.dragOffset.x = canvasX - node.x;
    state.dragOffset.y = canvasY - node.y;
    return;
  }
  
  // Check if click is on a connection line (select)
  const lineTarget = event.target.closest(".sld-line");
  if (lineTarget && lineTarget !== tempConnectionLine) {
    event.stopPropagation();
    const linkId = lineTarget.dataset.linkId;
    selectElement(linkId, "link");
    return;
  }
  
  // Fallback: Pan viewport (middle mouse OR left mouse on empty background)
  if (event.button === 1 || event.button === 0 || event.shiftKey) {
    state.isPanning = true;
    state.startPan.x = event.clientX - state.pan.x;
    state.startPan.y = event.clientY - state.pan.y;
    viewport.style.cursor = "grabbing";
  }
}

function handleMouseMove(event) {
  const rect = viewport.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const canvasX = (mouseX - state.pan.x) / state.zoom;
  const canvasY = (mouseY - state.pan.y) / state.zoom;
  
  if (state.isPanning) {
    state.pan.x = event.clientX - state.startPan.x;
    state.pan.y = event.clientY - state.startPan.y;
    updateViewportTransform();
    return;
  }
  
  if (state.draggedNode) {
    const node = state.nodes[state.draggedNode];
    if (!state.dragStarted) {
      pushHistory();
      state.dragStarted = true;
    }
    // Snap node coordinates to a 15px grid for AutoCAD layout feel
    const snapGrid = 15;
    let targetX = canvasX - state.dragOffset.x;
    let targetY = canvasY - state.dragOffset.y;
    
    node.x = Math.round(targetX / snapGrid) * snapGrid;
    node.y = Math.round(targetY / snapGrid) * snapGrid;
    
    // Clear results since topology changed
    state.hasResults = false;
    
    renderAll();
    return;
  }
  
  if (state.connectingPin) {
    // Render rubberband link
    const startX = state.connectingPin.x;
    const startY = state.connectingPin.y;
    const pathStr = drawOrthogonalPath(
      startX, startY, 
      canvasX, canvasY, 
      state.connectingPin.dir || { x: 0, y: -1 }, 
      { x: 0, y: 1 }
    );
    tempConnectionLine.setAttribute("d", pathStr);
  }
}

function handleMouseUp(event) {
  if (state.isPanning) {
    state.isPanning = false;
    viewport.style.cursor = "grab";
  }
  
  if (state.draggedNode) {
    state.draggedNode = null;
    state.dragStarted = false;
  }
  
  if (state.connectingPin) {
    tempConnectionLine.style.display = "none";
    
    // Check if mouse released over a pin
    const pinTarget = event.target.closest(".sld-pin");
    if (pinTarget) {
      const toNodeId = pinTarget.dataset.nodeId;
      const toPinName = pinTarget.dataset.pinName;
      createLink(state.connectingPin.nodeId, state.connectingPin.pinName, toNodeId, toPinName);
    }
    
    state.connectingPin = null;
  }
}

function fitCanvas() {
  const nodeIds = Object.keys(state.nodes);
  if (nodeIds.length === 0) {
    state.pan = { x: 50, y: 50 };
    state.zoom = 1.0;
    updateViewportTransform();
    return;
  }
  
  // Calculate bounding box of all nodes
  let minX = Infinity, minY = Infinity;
  let maxX = -Infinity, maxY = -Infinity;
  
  nodeIds.forEach(id => {
    const node = state.nodes[id];
    const size = NODE_SIZE[node.kind];
    minX = Math.min(minX, node.x);
    minY = Math.min(minY, node.y);
    maxX = Math.max(maxX, node.x + size.w);
    maxY = Math.max(maxY, node.y + size.h);
  });
  
  const pad = 60;
  const width = (maxX - minX) + pad * 2;
  const height = (maxY - minY) + pad * 2;
  const vpWidth = viewport.clientWidth;
  const vpHeight = viewport.clientHeight;
  
  // Calculate best zoom level to fit
  const scale = Math.min(vpWidth / width, vpHeight / height, 2.0);
  state.zoom = Math.max(0.3, scale);
  
  // Calculate offset to center the box
  const centerX = minX + (maxX - minX) / 2;
  const centerY = minY + (maxY - minY) / 2;
  
  state.pan.x = vpWidth / 2 - centerX * state.zoom;
  state.pan.y = vpHeight / 2 - centerY * state.zoom;
  
  updateViewportTransform();
}

// -------------------------------------------------------------
// Topology & Link Management
// -------------------------------------------------------------
function selectElement(id, type) {
  state.selectedId = id;
  state.selectedType = type;
  
  // Highlight visually
  renderAll();
  renderProperties();
}

function createLink(fromNode, fromPin, toNode, toPin) {
  if (fromNode === toNode) {
    showStatus("Tidak bisa menghubungkan ke komponen yang sama", "err");
    return;
  }
  
  // Check if link already exists
  const exists = Object.values(state.links).some(link => 
    (link.fromNode === fromNode && link.fromPin === fromPin && link.toNode === toNode && link.toPin === toPin) ||
    (link.fromNode === toNode && link.fromPin === toPin && link.toNode === fromNode && link.toPin === fromPin)
  );
  if (exists) {
    showStatus("Koneksi ini sudah ada", "warn");
    return;
  }
  
  // Validation Rules
  const fromKind = state.nodes[fromNode].kind;
  const toKind = state.nodes[toNode].kind;
  
  // Limit connection count for loads, generators, shunts, trafos to 1 link per terminal
  if (["load", "gen", "shunt"].includes(fromKind) && pinConnectedCount(fromNode, fromPin) >= 1) {
    showStatus(`Pin ${fromKind} sudah terhubung`, "warn");
    return;
  }
  if (["load", "gen", "shunt"].includes(toKind) && pinConnectedCount(toNode, toPin) >= 1) {
    showStatus(`Pin ${toKind} sudah terhubung`, "warn");
    return;
  }
  if (fromKind === "trafo" && pinConnectedCount(fromNode, fromPin) >= 1) {
    showStatus(`Terminal ${fromPin} Trafo sudah terhubung`, "warn");
    return;
  }
  if (toKind === "trafo" && pinConnectedCount(toNode, toPin) >= 1) {
    showStatus(`Terminal ${toPin} Trafo sudah terhubung`, "warn");
    return;
  }
  
  // Check valid type connection
  const allowed = validateConnectionRoles(fromKind, fromPin, toKind, toPin);
  if (!allowed.ok) {
    showStatus(allowed.msg, "err");
    return;
  }
  
  // Create link
  pushHistory();
  const linkId = `link-${state.nextId.line}`;
  state.nextId.line += 1;
  
  state.links[linkId] = {
    id: linkId,
    fromNode,
    fromPin,
    toNode,
    toPin,
    params: {
      label: `Line ${linkId.split('-')[1]}`,
      length_km: 0.05,
      r_ohm_per_km: 0.225,
      x_ohm_per_km: 0.08,
      c_nf_per_km: 264.0,
      max_i_ka: 0.242,
    }
  };
  
  state.hasResults = false;
  selectElement(linkId, "link");
  showStatus("Koneksi berhasil dibuat", "ok");
  renderAll();
}

function pinConnectedCount(nodeId, pinName) {
  return Object.values(state.links).filter(link => 
    (link.fromNode === nodeId && link.fromPin === pinName) ||
    (link.toNode === nodeId && link.toPin === pinName)
  ).length;
}

function validateConnectionRoles(k1, p1, k2, p2) {
  const roles = {
    bus: ["in", "in_2", "out", "out_2"],
    source: ["out"],
    trafo: ["hv", "lv"],
    load: ["pin"],
    gen: ["pin"],
    shunt: ["pin"]
  };
  
  // Bus to Bus: line
  if (k1 === "bus" && k2 === "bus") {
    // Normal bus to bus connection
    return { ok: true };
  }

  // External grid can feed transformer HV directly; backend maps it as a slack bus.
  if (k1 === "source" && k2 === "trafo") {
    if (p2 === "hv") return { ok: true };
    return { ok: false, msg: "External Grid harus tersambung ke terminal HV Transformer" };
  }
  if (k2 === "source" && k1 === "trafo") {
    if (p1 === "hv") return { ok: true };
    return { ok: false, msg: "External Grid harus tersambung ke terminal HV Transformer" };
  }
  
  // Slack (source) must connect to Bus input
  if (k1 === "source" && k2 === "bus") {
    if (p2.startsWith("in")) return { ok: true };
    return { ok: false, msg: "External Grid harus tersambung ke input Busbar" };
  }
  if (k2 === "source" && k1 === "bus") {
    if (p1.startsWith("in")) return { ok: true };
    return { ok: false, msg: "External Grid harus tersambung ke input Busbar" };
  }
  
  // Load / Shunt must connect to Bus output
  if (["load", "shunt"].includes(k1) && k2 === "bus") {
    if (p2.startsWith("out")) return { ok: true };
    return { ok: false, msg: "Beban / Shunt harus tersambung ke output Busbar" };
  }
  if (["load", "shunt"].includes(k2) && k1 === "bus") {
    if (p1.startsWith("out")) return { ok: true };
    return { ok: false, msg: "Beban / Shunt harus tersambung ke output Busbar" };
  }
  
  // Generator must connect to Bus input
  if (k1 === "gen" && k2 === "bus") {
    if (p2.startsWith("in")) return { ok: true };
    return { ok: false, msg: "Generator harus tersambung ke input Busbar" };
  }
  if (k2 === "gen" && k1 === "bus") {
    if (p1.startsWith("in")) return { ok: true };
    return { ok: false, msg: "Generator harus tersambung ke input Busbar" };
  }
  
  // Trafo HV connects to Bus output, Trafo LV connects to Bus input (step down)
  if (k1 === "trafo" && k2 === "bus") {
    if (p1 === "hv" && p2.startsWith("out")) return { ok: true };
    if (p1 === "lv" && p2.startsWith("in")) return { ok: true };
    return { ok: false, msg: "Koneksi Transformer: HV ke output Bus, LV ke input Bus" };
  }
  if (k2 === "trafo" && k1 === "bus") {
    if (p2 === "hv" && p1.startsWith("out")) return { ok: true };
    if (p2 === "lv" && p1.startsWith("in")) return { ok: true };
    return { ok: false, msg: "Koneksi Transformer: HV ke output Bus, LV ke input Bus" };
  }
  
  return { ok: false, msg: `Koneksi antar ${LABEL_BY_KIND[k1]} dan ${LABEL_BY_KIND[k2]} tidak didukung` };
}

// -------------------------------------------------------------
// Component Addition & Deletion
// -------------------------------------------------------------
function addComponent(kind) {
  pushHistory();
  const id = `${kind}-${state.nextId[kind]}`;
  state.nextId[kind] += 1;
  
  // Position in center of viewport
  const rect = viewport.getBoundingClientRect();
  const cx = (rect.width / 2 - state.pan.x) / state.zoom;
  const cy = (rect.height / 2 - state.pan.y) / state.zoom;
  const size = NODE_SIZE[kind];
  
  // Grid snap new components
  const px = Math.round((cx - size.w / 2) / 15) * 15;
  const py = Math.round((cy - size.h / 2) / 15) * 15;
  
  state.nodes[id] = {
    id,
    kind,
    label: `${LABEL_BY_KIND[kind]} ${id.split('-')[1]}`,
    x: px,
    y: py,
    params: {
      vn_kv: kind === "source" ? 10.0 : (kind === "trafo" ? 10.0 : 0.4),
      p_mw: kind === "load" ? 0.05 : (kind === "gen" ? 0.1 : 0.0),
      q_mvar: kind === "load" ? 0.015 : (kind === "gen" ? 0.02 : 0.0),
      is_slack: kind === "source", // Slack only for source
      vm_pu: 1.0,
      va_degree: 0.0,
      
      // Trafo params
      sn_mva: 0.25,
      vn_hv_kv: 10.0,
      vn_lv_kv: 0.4,
      vk_percent: 4.0,
      vkr_percent: 1.2,
      pfe_kw: 0.0,
      i0_percent: 0.0
    }
  };
  
  state.hasResults = false;
  selectElement(id, "node");
  showStatus(`Komponen ${LABEL_BY_KIND[kind]} ditambahkan`, "ok");
  renderAll();
}

function deleteSelected() {
  const id = state.selectedId;
  if (!id) return;
  
  pushHistory();
  
  if (state.selectedType === "node") {
    // Delete links connected to this node
    Object.keys(state.links).forEach(linkId => {
      const link = state.links[linkId];
      if (link.fromNode === id || link.toNode === id) {
        delete state.links[linkId];
      }
    });
    
    // Delete node
    delete state.nodes[id];
    showStatus(`Komponen ${id} berhasil dihapus`, "ok");
  } else if (state.selectedType === "link") {
    // Delete link
    delete state.links[id];
    showStatus(`Koneksi ${id} berhasil dihapus`, "ok");
  }
  
  state.selectedId = null;
  state.selectedType = null;
  state.hasResults = false;
  renderAll();
  renderProperties();
}

function newProject() {
  if (Object.keys(state.nodes).length > 0 && !confirm("Buat project baru? Semua komponen saat ini akan terhapus.")) {
    return;
  }
  
  state.nodes = {};
  state.links = {};
  state.undoStack = [];
  state.redoStack = [];
  state.selectedId = null;
  state.selectedType = null;
  state.nextId = normalizeNextId();
  state.hasResults = false;
  
  // Add slack bus by default
  const sid = `source-${state.nextId.source}`;
  state.nodes[sid] = {
    id: sid,
    kind: "source",
    label: "Slack Grid",
    x: 80,
    y: 200,
    params: { vn_kv: 10.0, is_slack: true, vm_pu: 1.0, va_degree: 0.0 }
  };
  state.nextId.source = 2;
  
  showStatus("Project baru berhasil dibuat", "ok");
  renderAll();
  renderProperties();
  fitCanvas();
}

// Populate radial template (Four Load Branch)
function loadTemplate() {
  if (Object.keys(state.nodes).length > 0 && !confirm("Muat template? Semua komponen saat ini akan terhapus.")) {
    return;
  }
  
  state.nodes = {};
  state.links = {};
  state.undoStack = [];
  state.redoStack = [];
  state.selectedId = null;
  state.selectedType = null;
  state.nextId = normalizeNextId({ bus: 6, load: 5, gen: 1, shunt: 1, trafo: 2, line: 11, source: 2 });
  state.hasResults = false;
  
  // Adding components for radial template
  state.nodes["source-1"] = {
    id: "source-1", kind: "source", label: "Ext Grid", x: 60, y: 195,
    params: { vn_kv: 10.0, is_slack: true, vm_pu: 1.0, va_degree: 0.0 }
  };
  
  state.nodes["trafo-1"] = {
    id: "trafo-1", kind: "trafo", label: "Trafo 10/0.4 kV", x: 220, y: 195,
    params: {
      vn_hv_kv: 10.0, vn_lv_kv: 0.4, sn_mva: 0.25,
      vk_percent: 4.0, vkr_percent: 1.2, pfe_kw: 0.0, i0_percent: 0.0
    }
  };
  
  state.nodes["bus-1"] = {
    id: "bus-1", kind: "bus", label: "Busbar Utama", x: 400, y: 210,
    params: { vn_kv: 0.4 }
  };
  
  state.nodes["bus-2"] = {
    id: "bus-2", kind: "bus", label: "Busbar 2", x: 590, y: 90,
    params: { vn_kv: 0.4 }
  };
  
  state.nodes["bus-3"] = {
    id: "bus-3", kind: "bus", label: "Busbar 3", x: 590, y: 315,
    params: { vn_kv: 0.4 }
  };
  
  state.nodes["bus-4"] = {
    id: "bus-4", kind: "bus", label: "Busbar 4", x: 780, y: 90,
    params: { vn_kv: 0.4 }
  };
  
  state.nodes["bus-5"] = {
    id: "bus-5", kind: "bus", label: "Busbar 5", x: 780, y: 315,
    params: { vn_kv: 0.4 }
  };
  
  // Adding loads
  for (let i = 1; i <= 4; i++) {
    const parentBus = i === 1 ? 2 : (i === 2 ? 3 : (i === 3 ? 4 : 5));
    const busNode = `bus-${parentBus}`;
    const loadId = `load-${i}`;
    const by = parentBus % 2 === 0 ? 15 : 375; // Y positions
    state.nodes[loadId] = {
      id: loadId, kind: "load", label: `Beban ${i}`, x: 600 + (parentBus >= 4 ? 190 : 0), y: by,
      params: { p_mw: 0.03, q_mvar: 0.01 }
    };
  }
  
  // Adding connections (Links)
  state.links["link-1"] = { id: "link-1", fromNode: "source-1", fromPin: "out", toNode: "trafo-1", toPin: "hv", params: {} };
  state.links["link-2"] = { id: "link-2", fromNode: "trafo-1", fromPin: "lv", toNode: "bus-1", toPin: "in", params: {} };
  
  const lineParams = { length_km: 0.05, r_ohm_per_km: 0.225, x_ohm_per_km: 0.08, c_nf_per_km: 264.0, max_i_ka: 0.242 };
  
  // Bus 1 -> Bus 2
  state.links["link-3"] = { 
    id: "link-3", fromNode: "bus-1", fromPin: "out", toNode: "bus-2", toPin: "in", 
    params: { label: "Line 1", ...lineParams } 
  };
  // Bus 1 -> Bus 3
  state.links["link-4"] = { 
    id: "link-4", fromNode: "bus-1", fromPin: "out_2", toNode: "bus-3", toPin: "in", 
    params: { label: "Line 2", ...lineParams } 
  };
  // Bus 2 -> Bus 4
  state.links["link-5"] = { 
    id: "link-5", fromNode: "bus-2", fromPin: "out_2", toNode: "bus-4", toPin: "in", 
    params: { label: "Line 3", ...lineParams } 
  };
  // Bus 3 -> Bus 5
  state.links["link-6"] = { 
    id: "link-6", fromNode: "bus-3", fromPin: "out_2", toNode: "bus-5", toPin: "in", 
    params: { label: "Line 4", ...lineParams } 
  };
  
  // Loads connections
  state.links["link-7"] = { id: "link-7", fromNode: "bus-2", fromPin: "out", toNode: "load-1", toPin: "pin", params: {} };
  state.links["link-8"] = { id: "link-8", fromNode: "bus-3", fromPin: "out", toNode: "load-2", toPin: "pin", params: {} };
  state.links["link-9"] = { id: "link-9", fromNode: "bus-4", fromPin: "out", toNode: "load-3", toPin: "pin", params: {} };
  state.links["link-10"] = { id: "link-10", fromNode: "bus-5", fromPin: "out", toNode: "load-4", toPin: "pin", params: {} };
  
  showStatus("Template Four Load Branch dimuat", "ok");
  renderAll();
  renderProperties();
  fitCanvas();
}

// -------------------------------------------------------------
// Real-time Source Tracing Engine
// -------------------------------------------------------------
function runSourceTracing() {
  const nodes = state.nodes;
  const links = state.links;
  
  // Build adjacency list representation of grid (undirected)
  const adj = {};
  Object.keys(nodes).forEach(id => adj[id] = []);
  
  // Maintain mapping of links
  const linkEdges = {};
  
  Object.keys(links).forEach(linkId => {
    const link = links[linkId];
    if (nodes[link.fromNode] && nodes[link.toNode]) {
      adj[link.fromNode].push({ to: link.toNode, linkId });
      adj[link.toNode].push({ to: link.fromNode, linkId });
      linkEdges[linkId] = { u: link.fromNode, v: link.toNode };
    }
  });
  
  // Find all sources (Slack nodes)
  const slacks = Object.values(nodes).filter(node => node.kind === "source");
  
  const nodeSourceMap = {}; // nodeId -> slackIndex (which source feeds this node)
  const linkSourceMap = {}; // linkId -> slackIndex
  
  // BFS/DFS traversal from each slack bus
  slacks.forEach((slack, index) => {
    const queue = [slack.id];
    const visited = new Set([slack.id]);
    nodeSourceMap[slack.id] = index;
    
    while (queue.length > 0) {
      const u = queue.shift();
      
      adj[u].forEach(edge => {
        const v = edge.to;
        if (!visited.has(v)) {
          visited.add(v);
          nodeSourceMap[v] = index;
          linkSourceMap[edge.linkId] = index;
          queue.push(v);
        } else {
          // If already visited, mark the connecting link as well
          linkSourceMap[edge.linkId] = index;
        }
      });
    }
  });
  
  return { nodeSourceMap, linkSourceMap };
}

// -------------------------------------------------------------
// Orthogonal Elbow Path Routing Algorithm
// -------------------------------------------------------------
function drawOrthogonalPath(x1, y1, x2, y2, dir1, dir2) {
  // Simple orthogonal routing with bends
  const dx = x2 - x1;
  const dy = y2 - y1;
  
  // If points are very close, draw simple line
  if (Math.hypot(dx, dy) < 10) {
    return `M ${x1} ${y1} L ${x2} ${y2}`;
  }
  
  let points = [{ x: x1, y: y1 }];
  
  // Exiting direction 1 offsets
  const extDist = 18;
  const p1_ext = { x: x1 + dir1.x * extDist, y: y1 + dir1.y * extDist };
  points.push(p1_ext);
  
  // Entrance direction 2 offsets
  const p2_ext = { x: x2 - dir2.x * extDist, y: y2 - dir2.y * extDist };
  
  // Complete the path orthogonally between the extension points
  if (dir1.x !== 0) { // Horizontal starting exit
    if (Math.sign(p2_ext.x - p1_ext.x) === Math.sign(dir1.x) || Math.abs(p2_ext.y - p1_ext.y) < 15) {
      // Step in X, then step in Y to target
      points.push({ x: p2_ext.x, y: p1_ext.y });
    } else {
      // Step Z bend: midpoint X, step Y, step X
      const midX = p1_ext.x + (p2_ext.x - p1_ext.x) / 2;
      points.push({ x: midX, y: p1_ext.y });
      points.push({ x: midX, y: p2_ext.y });
    }
  } else { // Vertical starting exit
    if (Math.sign(p2_ext.y - p1_ext.y) === Math.sign(dir1.y) || Math.abs(p2_ext.x - p1_ext.x) < 15) {
      // Step in Y, then step in X to target
      points.push({ x: p1_ext.x, y: p2_ext.y });
    } else {
      // Step Z bend: midpoint Y, step X, step Y
      const midY = p1_ext.y + (p2_ext.y - p1_ext.y) / 2;
      points.push({ x: p1_ext.x, y: midY });
      points.push({ x: p2_ext.x, y: midY });
    }
  }
  
  points.push(p2_ext);
  points.push({ x: x2, y: y2 });
  
  // Convert points to SVG Path command
  const [first, ...rest] = points;
  return `M ${first.x} ${first.y} ` + rest.map(p => `L ${p.x} ${p.y}`).join(" ");
}

// -------------------------------------------------------------
// Rendering Canvas Elements
// -------------------------------------------------------------
function renderAll() {
  const trace = runSourceTracing();
  
  renderLinks(trace.linkSourceMap);
  renderNodes(trace.nodeSourceMap);
  
  // Summary counts
  renderSummary();
  renderResults();
  
  // Set count
  const nNodes = Object.keys(state.nodes).length;
  const nLinks = Object.values(state.links).filter(link => 
    state.nodes[link.fromNode] && state.nodes[link.toNode] && 
    state.nodes[link.fromNode].kind === "bus" && state.nodes[link.toNode].kind === "bus"
  ).length;
  canvasMeta.textContent = `${nNodes} komponen, ${nLinks} saluran transmisi`;
}

function renderLinks(linkSourceMap) {
  linksGroup.innerHTML = "";
  
  Object.keys(state.links).forEach(linkId => {
    const link = state.links[linkId];
    const fromNode = state.nodes[link.fromNode];
    const toNode = state.nodes[link.toNode];
    if (!fromNode || !toNode) return; // dangling link
    
    const p1 = getPinCoords(link.fromNode, link.fromPin);
    const p2 = getPinCoords(link.toNode, link.toPin);
    
    // Draw ortholine path
    const pathStr = drawOrthogonalPath(p1.x, p1.y, p2.x, p2.y, p1.dir, p2.dir);
    
    const isSelected = linkId === state.selectedId && state.selectedType === "link" ? "selected" : "";
    
    // Determine path color theme
    let colorClass = "feeder-island";
    const sourceIdx = linkSourceMap[linkId];
    if (sourceIdx !== undefined) {
      colorClass = `feeder-slack-${sourceIdx % 5}`;
    }
    
    // Override color class if simulation has results
    if (state.hasResults && state.results.links[linkId]) {
      const pct = state.results.links[linkId].loading_percent;
      if (pct >= 90) colorClass = "load-flow-danger";
      else if (pct >= 70) colorClass = "load-flow-warn";
      else colorClass = "load-flow-safe";
    }
    
    const pathElement = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pathElement.setAttribute("class", `sld-line ${colorClass} ${isSelected}`);
    pathElement.setAttribute("d", pathStr);
    pathElement.setAttribute("data-link-id", linkId);
    
    // Double lines or glow effect for selected
    linksGroup.appendChild(pathElement);
    
    // Junction connector dot if it enters the side of another busbar
    // (This improves AutoCAD aesthetic when routing overlaps a Bus)
  });
}

function getHeaderPath(w, h, r) {
  if (r === 0) return `M 0 0 L ${w} 0 L ${w} ${h} L 0 ${h} Z`;
  return `M 0 ${r} A ${r} ${r} 0 0 1 ${r} 0 L ${w - r} 0 A ${r} ${r} 0 0 1 ${w} ${r} L ${w} ${h} L 0 ${h} Z`;
}

function renderNodes(nodeSourceMap) {
  nodesGroup.innerHTML = "";
  
  Object.keys(state.nodes).forEach(id => {
    const node = state.nodes[id];
    const size = NODE_SIZE[node.kind];
    const isSelected = id === state.selectedId && state.selectedType === "node" ? "selected" : "";
    
    // Node Group Wrapper
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", `sld-node-group ${isSelected}`);
    g.setAttribute("transform", `translate(${node.x}, ${node.y})`);
    g.setAttribute("data-node-id", id);
    
    // Determine corner rounding and format content lines
    let r = 4;
    let titleStr = "";
    let lines = [];
    const params = node.params || {};
    
    if (node.kind === "source") {
      r = 4;
      titleStr = `[SLACK] ${node.label}`;
      const vVal = state.hasResults && state.results.nodes[id] 
        ? `V ${state.results.nodes[id].vm_pu.toFixed(4)} pu` 
        : `V --`;
      const vaVal = state.hasResults && state.results.nodes[id] 
        ? `va ${state.results.nodes[id].va_degree.toFixed(1)} deg` 
        : `va --`;
      lines = [
        { text: `Slack ${params.vn_kv ? params.vn_kv.toFixed(1) : "10.0"} kV`, colorClass: "line-slack" },
        { text: vVal, colorClass: "line-val" },
        { text: vaVal, colorClass: "line-val" },
        { text: "IN", colorClass: "line-gray" }
      ];
    } else if (node.kind === "bus") {
      r = 4;
      const isSlack = params.is_slack;
      titleStr = isSlack ? `[SLACK] ${node.label}` : `[BUS] ${node.label}`;
      const vVal = state.hasResults && state.results.nodes[id] 
        ? `V ${state.results.nodes[id].vm_pu.toFixed(4)} pu` 
        : `V --`;
      const vaVal = state.hasResults && state.results.nodes[id] 
        ? `va ${state.results.nodes[id].va_degree.toFixed(1)} deg` 
        : `va --`;
      lines = [
        { text: `${isSlack ? "Slack" : "Vn"} ${params.vn_kv ? params.vn_kv.toFixed(1) : "0.4"} kV`, colorClass: isSlack ? "line-slack" : "line-bus" },
        { text: vVal, colorClass: "line-val" },
        { text: vaVal, colorClass: "line-val" },
        { text: "IN", colorClass: "line-gray" }
      ];
    } else if (node.kind === "gen") {
      r = 12;
      titleStr = `(G) ${node.label}`;
      lines = [
        { text: "GEN", colorClass: "line-gen" },
        { text: `P ${params.p_mw ? params.p_mw.toFixed(2) : "1.00"} MW`, colorClass: "line-val" },
        { text: `Q ${params.q_mvar ? params.q_mvar.toFixed(2) : "0.00"} MVAr`, colorClass: "line-val" }
      ];
    } else if (node.kind === "trafo") {
      r = 6;
      titleStr = `[T] ${node.label}`;
      lines = [
        { text: `HV ${params.vn_hv_kv ? params.vn_hv_kv.toFixed(1) : "110.0"} kV`, colorClass: "line-trafo" },
        { text: `S ${params.sn_mva ? params.sn_mva.toFixed(2) : "10.00"} MVA`, colorClass: "line-val" },
        { text: `${params.vn_hv_kv ? params.vn_hv_kv.toFixed(1) : "110.0"}/${params.vn_lv_kv ? params.vn_lv_kv.toFixed(1) : "20.0"} kV`, colorClass: "line-val" },
        { text: `LV ${params.vn_lv_kv ? params.vn_lv_kv.toFixed(1) : "20.0"} kV`, colorClass: "line-trafo" }
      ];
    } else if (node.kind === "load") {
      r = 6;
      titleStr = `(L) ${node.label}`;
      lines = [
        { text: "LOAD", colorClass: "line-load" },
        { text: `P ${params.p_mw ? params.p_mw.toFixed(2) : "0.50"} MW`, colorClass: "line-val" },
        { text: `Q ${params.q_mvar ? params.q_mvar.toFixed(2) : "0.10"} MVAr`, colorClass: "line-val" }
      ];
    } else if (node.kind === "shunt") {
      r = 2;
      titleStr = `(C) ${node.label}`;
      lines = [
        { text: "SHUNT", colorClass: "line-shunt" },
        { text: `P ${params.p_mw ? params.p_mw.toFixed(2) : "0.00"} MW`, colorClass: "line-val" },
        { text: `Q ${params.q_mvar ? params.q_mvar.toFixed(2) : "-1.00"} MVAr`, colorClass: "line-val" }
      ];
    }

    // 1. Box Background
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("class", `sld-node-bg sld-node-${node.kind}`);
    bg.setAttribute("width", size.w);
    bg.setAttribute("height", size.h);
    bg.setAttribute("rx", r);
    bg.setAttribute("ry", r);
    g.appendChild(bg);
    
    // 2. Header Bar
    const header = document.createElementNS("http://www.w3.org/2000/svg", "path");
    header.setAttribute("class", `sld-node-header header-${node.kind}`);
    header.setAttribute("d", getHeaderPath(size.w, 24, r));
    g.appendChild(header);
    
    // 3. Title Text
    const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
    title.setAttribute("class", "sld-node-title");
    title.setAttribute("x", 8);
    title.setAttribute("y", 16);
    title.textContent = titleStr;
    g.appendChild(title);
    
    // 4. Body Content Lines
    lines.forEach((line, index) => {
      const textEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      textEl.setAttribute("class", `sld-node-body-line ${line.colorClass}`);
      textEl.setAttribute("x", 8);
      textEl.setAttribute("y", 40 + index * 18);
      textEl.textContent = line.text;
      g.appendChild(textEl);
    });
    
    // 5. Connection Pin Indicators (rendered on top of borders)
    const pins = getPins(node);
    pins.forEach(pin => {
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("class", "sld-pin");
      circle.setAttribute("cx", pin.cx - node.x);
      circle.setAttribute("cy", pin.cy - node.y);
      circle.setAttribute("r", 4);
      circle.setAttribute("data-node-id", id);
      circle.setAttribute("data-pinName", pin.name);
      g.appendChild(circle);
    });
    
    nodesGroup.appendChild(g);
  });
}

function getMetaText(node) {
  const p = node.params;
  if (node.kind === "source") return `${p.vn_kv.toFixed(1)} kV (Slack)`;
  if (node.kind === "bus") return `${p.vn_kv.toFixed(2)} kV`;
  if (node.kind === "trafo") return `${p.sn_mva.toFixed(2)} MVA`;
  if (node.kind === "load") return `P: ${p.p_mw.toFixed(3)} MW`;
  if (node.kind === "gen") return `P: ${p.p_mw.toFixed(2)} MW`;
  if (node.kind === "shunt") return `Q: ${p.q_mvar.toFixed(2)} MVAr`;
  return "";
}

function voltageToneClass(vm) {
  if (vm >= 0.95 && vm <= 1.05) return "ok";
  if (vm >= 0.90 && vm <= 1.10) return "warn";
  return "bad";
}

// -------------------------------------------------------------
// Validation & Solver client
// -------------------------------------------------------------
function validateNetwork() {
  const errors = [];
  const warnings = [];
  
  const nodes = Object.values(state.nodes);
  const links = Object.values(state.links);
  
  const buses = nodes.filter(n => n.kind === "bus");
  const slacks = nodes.filter(n => n.kind === "source");
  
  if (nodes.length === 0) {
    errors.push("Kanvas jaringan kosong.");
  }
  if (buses.length < 2) {
    errors.push("Membutuhkan minimal 2 Busbar untuk mensimulasikan aliran daya.");
  }
  if (slacks.length === 0) {
    errors.push("Tidak ada Slack Bus / External Grid sebagai jangkar referensi.");
  }
  if (slacks.length > 1) {
    warnings.push("Terdapat lebih dari satu Slack Bus dalam sistem.");
  }
  if (links.length === 0) {
    errors.push("Belum ada koneksi antar komponen.");
  }
  
  // Slack Connection Tracing
  const trace = runSourceTracing();
  buses.forEach(bus => {
    if (trace.nodeSourceMap[bus.id] === undefined) {
      errors.push(`Busbar [${bus.label}] tidak terhubung ke Slack Bus / External Grid.`);
    }
  });
  
  // Nominal voltage matching on Lines
  links.forEach(link => {
    const fromNode = state.nodes[link.fromNode];
    const toNode = state.nodes[link.toNode];
    if (fromNode && toNode && fromNode.kind === "bus" && toNode.kind === "bus") {
      const v1 = fromNode.params.vn_kv;
      const v2 = toNode.params.vn_kv;
      if (Math.abs(v1 - v2) > 0.001) {
        errors.push(`Saluran [${link.params.label || link.id}] menghubungkan dua bus dengan nominal tegangan berbeda: ${fromNode.label} (${v1} kV) dan ${toNode.label} (${v2} kV).`);
      }
    }
  });
  
  state.validationErrors = errors;
  state.validationWarnings = warnings;
  
  // Update status pill & side box
  if (errors.length > 0) {
    showStatus("Masalah Jaringan", "err");
  } else if (warnings.length > 0) {
    showStatus("Validasi Peringatan", "warn");
  } else {
    showStatus("Jaringan OK", "ok");
  }
  
  renderSummary();
}

function runPowerFlowSimulation() {
  validateNetwork();
  if (state.validationErrors.length > 0) {
    alert("Jaringan tidak valid! Silakan cek panel Ringkasan untuk daftar kesalahan.");
    return;
  }
  
  showStatus("Menghitung...", "warn");
  
  // Format network JSON payload matching the backend's expected structure
  const payload = {
    nodes: Object.keys(state.nodes).map(id => {
      const node = state.nodes[id];
      return {
        id,
        kind: node.kind,
        label: node.label,
        vn_kv: Number(node.params.vn_kv),
        is_slack: Boolean(node.params.is_slack),
        vm_pu: Number(node.params.vm_pu),
        va_degree: Number(node.params.va_degree),
        p_mw: Number(node.params.p_mw),
        q_mvar: Number(node.params.q_mvar),
        sn_mva: Number(node.params.sn_mva),
        vn_hv_kv: Number(node.params.vn_hv_kv),
        vn_lv_kv: Number(node.params.vn_lv_kv),
        vk_percent: Number(node.params.vk_percent),
        vkr_percent: Number(node.params.vkr_percent),
        pfe_kw: Number(node.params.pfe_kw),
        i0_percent: Number(node.params.i0_percent),
        pos: [node.x, node.y]
      };
    }),
    links: Object.keys(state.links).map(id => {
      const link = state.links[id];
      return {
        id,
        fromNode: link.fromNode,
        fromPin: link.fromPin,
        toNode: link.toNode,
        toPin: link.toPin,
        line_data: link.params
      };
    })
  };
  
  // Check if running inside Python PyWebView
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.simulate(payload)
      .then(data => {
        if (data.ok) {
          state.results = data.results;
          state.hasResults = true;
          showStatus("Konvergen (OK)", "ok");
          renderAll();
        } else {
          state.hasResults = false;
          showStatus("Gagal Konvergen", "err");
          alert("Simulasi Gagal: " + data.message);
        }
      })
      .catch(err => {
        console.error(err);
        state.hasResults = false;
        showStatus("Bridge Error", "err");
      });
    return;
  }

  fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
  .then(res => {
    if (!res.ok) throw new Error("API Server error");
    return res.json();
  })
  .then(data => {
    if (data.ok) {
      state.results = data.results;
      state.hasResults = true;
      showStatus("Konvergen (OK)", "ok");
      renderAll();
    } else {
      state.hasResults = false;
      showStatus("Gagal Konvergen", "err");
      alert("Simulasi Gagal: " + data.message);
    }
  })
  .catch(err => {
    console.error(err);
    state.hasResults = false;
    showStatus("Koneksi Error", "err");
    
    // MOCK SIMULATION FOR DEMO PURPOSES IF PYTHON BACKEND IS DOWN
    mockSimulation(payload);
  });
}

function mockSimulation(payload) {
  // Simulates dummy values so the user is not blocked if Python server is not yet running
  showStatus("Konvergen (Mock)", "warn");
  
  const nodesRes = {};
  const linksRes = {};
  
  // Calculate voltage drop simulation
  let busIdx = 0;
  Object.keys(state.nodes).forEach(id => {
    const node = state.nodes[id];
    if (node.kind === "bus") {
      const drop = Math.min(busIdx * 0.008, 0.06);
      nodesRes[id] = {
        table: "bus",
        vm_pu: 1.0 - drop,
        va_degree: -0.5 - busIdx * 0.4,
        p_mw: 0.05,
        q_mvar: 0.02
      };
      busIdx++;
    } else if (["load", "gen", "shunt"].includes(node.kind)) {
      nodesRes[id] = {
        table: node.kind,
        p_mw: node.params.p_mw,
        q_mvar: node.params.q_mvar
      };
    }
  });
  
  // Calculate line load simulation
  let linkIdx = 0;
  Object.keys(state.links).forEach(id => {
    const loading = Math.max(15, 84 - linkIdx * 15);
    linksRes[id] = {
      table: "line",
      loading_percent: loading,
      p_from_mw: 0.12 - linkIdx * 0.02,
      q_from_mvar: 0.04 - linkIdx * 0.01,
      pl_mw: 0.0012,
      pl_kw: 1.2
    };
    linkIdx++;
  });
  
  state.results = { nodes: nodesRes, links: linksRes };
  state.hasResults = true;
  renderAll();
}

// -------------------------------------------------------------
// Sidebars Rendering (Summary & Properties)
// -------------------------------------------------------------
function renderSummary() {
  const counts = { bus: 0, trafo: 0, load: 0, gen: 0, shunt: 0, source: 0 };
  Object.values(state.nodes).forEach(node => {
    if (counts[node.kind] !== undefined) counts[node.kind]++;
  });
  
  const totalLoadP = Object.values(state.nodes)
    .filter(n => n.kind === "load")
    .reduce((sum, n) => sum + Number(n.params.p_mw || 0), 0);
    
  const totalGenP = Object.values(state.nodes)
    .filter(n => n.kind === "gen")
    .reduce((sum, n) => sum + Number(n.params.p_mw || 0), 0);
    
  let maxLoading = 0;
  if (state.hasResults) {
    maxLoading = Object.values(state.results.links).reduce((max, r) => Math.max(max, r.loading_percent || 0), 0);
  }
  
  summaryGrid.innerHTML = `
    <dt>External Grid</dt><dd>${counts.source}</dd>
    <dt>Busbar</dt><dd>${counts.bus}</dd>
    <dt>Transformer</dt><dd>${counts.trafo}</dd>
    <dt>Beban (Load)</dt><dd>${counts.load}</dd>
    <dt>Generator</dt><dd>${counts.gen}</dd>
    <dt>Shunt Komp.</dt><dd>${counts.shunt}</dd>
    <dt>Total Beban P</dt><dd>${totalLoadP.toFixed(3)} MW</dd>
    <dt>Total Pembangkit</dt><dd>${totalGenP.toFixed(2)} MW</dd>
    <dt>Beban Saluran Maks</dt><dd>${state.hasResults ? maxLoading.toFixed(1) + ' %' : '--'}</dd>
  `;
  
  // Validation messages rendering
  if (state.validationErrors.length === 0) {
    validationBox.className = "validation-box ok";
    validationBox.innerHTML = state.hasResults ? ">> STATUS: BALANCED (RESULTS READY)" : ">> STATUS: VALID (READY TO SIMULATE)";
  } else {
    validationBox.className = "validation-box err";
    validationBox.innerHTML = state.validationErrors.map(err => `<div class="validation-error-item">>> ERR: ${err}</div>`).join("");
  }
}

function renderResults() {
  resultState.textContent = state.hasResults ? "ONLINE / CONVERGED" : "OFFLINE / IDLE";
  
  // Filter only links that have loading values
  const rows = [];
  Object.keys(state.links).forEach(id => {
    const link = state.links[id];
    const res = state.results.links[id];
    if (res) {
      rows.push({
        name: link.params.label || id,
        kind: state.nodes[link.fromNode].kind === "bus" && state.nodes[link.toNode].kind === "bus" ? "Line" : "Trafo Link",
        p: res.p_from_mw !== undefined ? res.p_from_mw : (res.p_hv_mw || 0),
        q: res.q_from_mvar !== undefined ? res.q_from_mvar : (res.q_hv_mvar || 0),
        loss: res.pl_mw !== undefined ? res.pl_mw * 1000 : (res.pl_mw * 1000 || 0),
        loading: res.loading_percent || 0
      });
    }
  });
  
  if (rows.length === 0) {
    resultRows.innerHTML = `<tr><td colspan="6" class="empty-results">Tidak ada data hasil simulasi.</td></tr>`;
    return;
  }
  
  resultRows.innerHTML = rows.map(row => {
    const tone = row.loading >= 90 ? "bad" : (row.loading >= 70 ? "warn" : "good");
    return `
      <tr>
        <td><strong>${row.name}</strong></td>
        <td>${row.kind}</td>
        <td>${row.p.toFixed(4)} MW</td>
        <td>${row.q.toFixed(4)} MVAr</td>
        <td>${row.loss.toFixed(2)} kW</td>
        <td class="${tone}">${row.loading.toFixed(1)} %</td>
      </tr>
    `;
  }).join("");
}

function renderProperties() {
  const id = state.selectedId;
  const type = state.selectedType;
  
  if (!id) {
    selectedKind.textContent = "Tidak ada pilihan";
    propertiesBody.innerHTML = `<div class="empty-state">Pilih komponen pada diagram untuk melihat propertinya.</div>`;
    return;
  }
  
  if (type === "node") {
    const node = state.nodes[id];
    selectedKind.textContent = LABEL_BY_KIND[node.kind];
    
    let editSection = `
      <div class="prop-block">
        <div class="prop-title">Parameter Dasar</div>
        <label class="field">
          <span>Label Komponen</span>
          <input type="text" id="propLabel" value="${node.label}">
        </label>
        <label class="field">
          <span>Posisi X</span>
          <input type="number" id="propX" value="${node.x}">
        </label>
        <label class="field">
          <span>Posisi Y</span>
          <input type="number" id="propY" value="${node.y}">
        </label>
      </div>
    `;
    
    // Add specific fields
    const p = node.params;
    if (node.kind === "bus" || node.kind === "source") {
      editSection += `
        <div class="prop-block">
          <div class="prop-title">Spesifikasi Bus</div>
          <label class="field">
            <span>Tegangan Nominal (kV)</span>
            <input type="number" step="0.05" id="param_vn_kv" value="${p.vn_kv}">
          </label>
          ${node.kind === "source" ? `
            <label class="field">
              <span>Tegangan Setpoint (pu)</span>
              <input type="number" step="0.01" id="param_vm_pu" value="${p.vm_pu || 1.0}">
            </label>
            <label class="field">
              <span>Sudut Tegangan (deg)</span>
              <input type="number" step="1.0" id="param_va_degree" value="${p.va_degree || 0.0}">
            </label>
          ` : ""}
        </div>
      `;
    } else if (["load", "gen", "shunt"].includes(node.kind)) {
      editSection += `
        <div class="prop-block">
          <div class="prop-title">Nilai Beban / Daya</div>
          <label class="field">
            <span>Daya Aktif P (MW)</span>
            <input type="number" step="0.005" id="param_p_mw" value="${p.p_mw}">
          </label>
          <label class="field">
            <span>Daya Reaktif Q (MVAr)</span>
            <input type="number" step="0.005" id="param_q_mvar" value="${p.q_mvar}">
          </label>
        </div>
      `;
    } else if (node.kind === "trafo") {
      editSection += `
        <div class="prop-block">
          <div class="prop-title">Parameter Trafo</div>
          <label class="field">
            <span>Daya Nominal (MVA)</span>
            <input type="number" step="0.05" id="param_sn_mva" value="${p.sn_mva}">
          </label>
          <label class="field">
            <span>Tegangan HV (kV)</span>
            <input type="number" step="1" id="param_vn_hv_kv" value="${p.vn_hv_kv}">
          </label>
          <label class="field">
            <span>Tegangan LV (kV)</span>
            <input type="number" step="0.05" id="param_vn_lv_kv" value="${p.vn_lv_kv}">
          </label>
          <label class="field">
            <span>Impedansi Hub-Singkat vk (%)</span>
            <input type="number" step="0.1" id="param_vk_percent" value="${p.vk_percent}">
          </label>
          <label class="field">
            <span>Resistansi Hub-Singkat vkr (%)</span>
            <input type="number" step="0.1" id="param_vkr_percent" value="${p.vkr_percent}">
          </label>
        </div>
      `;
    }
    
    // Add deletion button
    editSection += `
      <div class="prop-block">
        <button class="panel-btn accent" id="btnDeleteSelectedProp" style="border-color: rgba(255, 71, 87, 0.4); background: rgba(255, 71, 87, 0.1); color: #ffa6a6;">Hapus Komponen</button>
      </div>
    `;
    
    // Add simulation results if available
    const result = state.results.nodes[id];
    if (state.hasResults && result) {
      editSection += `
        <div class="prop-block">
          <div class="prop-title">Hasil Simulasi Terakhir</div>
          <dl class="prop-list">
            <dt>Tipe Data</dt><dd>${result.table}</dd>
            ${result.vm_pu !== undefined ? `<dt>Voltase</dt><dd>${result.vm_pu.toFixed(4)} pu</dd>` : ""}
            ${result.va_degree !== undefined ? `<dt>Sudut va</dt><dd>${result.va_degree.toFixed(2)} deg</dd>` : ""}
            ${result.p_mw !== undefined ? `<dt>Aliran P</dt><dd>${result.p_mw.toFixed(4)} MW</dd>` : ""}
            ${result.q_mvar !== undefined ? `<dt>Aliran Q</dt><dd>${result.q_mvar.toFixed(4)} MVAr</dd>` : ""}
          </dl>
        </div>
      `;
    }
    
    propertiesBody.innerHTML = editSection;
    attachPropertyListeners(id, "node");
    
  } else if (type === "link") {
    const link = state.links[id];
    selectedKind.textContent = "Saluran Transmisi";
    
    const lp = link.params;
    let editSection = `
      <div class="prop-block">
        <div class="prop-title">Parameter Saluran</div>
        <label class="field">
          <span>Label Saluran</span>
          <input type="text" id="propLabel" value="${lp.label || id}">
        </label>
        <label class="field">
          <span>Panjang Kabel (km)</span>
          <input type="number" step="0.01" id="line_length_km" value="${lp.length_km}">
        </label>
        <label class="field">
          <span>Resistansi R (Ohm/km)</span>
          <input type="number" step="0.001" id="line_r_ohm_per_km" value="${lp.r_ohm_per_km}">
        </label>
        <label class="field">
          <span>Reaktansi X (Ohm/km)</span>
          <input type="number" step="0.001" id="line_x_ohm_per_km" value="${lp.x_ohm_per_km}">
        </label>
        <label class="field">
          <span>Kapasitansi C (nF/km)</span>
          <input type="number" step="1.0" id="line_c_nf_per_km" value="${lp.c_nf_per_km}">
        </label>
        <label class="field">
          <span>Arus Maksimum (kA)</span>
          <input type="number" step="0.01" id="line_max_i_ka" value="${lp.max_i_ka}">
        </label>
      </div>
      <div class="prop-block">
        <button class="panel-btn accent" id="btnDeleteSelectedProp" style="border-color: rgba(255, 71, 87, 0.4); background: rgba(255, 71, 87, 0.1); color: #ffa6a6;">Hapus Koneksi</button>
      </div>
    `;
    
    // Add simulation results if available
    const result = state.results.links[id];
    if (state.hasResults && result) {
      editSection += `
        <div class="prop-block">
          <div class="prop-title">Hasil Simulasi Terakhir</div>
          <dl class="prop-list">
            <dt>Persen Beban</dt><dd class="${result.loading_percent >= 90 ? 'bad' : 'good'}" style="color: ${result.loading_percent >= 90 ? 'var(--danger)' : 'var(--success)'}">${result.loading_percent.toFixed(1)} %</dd>
            <dt>Arus Mengalir</dt><dd>${(result.i_from_ka || 0).toFixed(4)} kA</dd>
            <dt>Daya Aktif P</dt><dd>${(result.p_from_mw || 0).toFixed(4)} MW</dd>
            <dt>Daya Reaktif Q</dt><dd>${(result.q_from_mvar || 0).toFixed(4)} MVAr</dd>
            <dt>Rugi Daya Ploss</dt><dd>${((result.pl_mw || 0) * 1000).toFixed(2)} kW</dd>
          </dl>
        </div>
      `;
    }
    
    propertiesBody.innerHTML = editSection;
    attachPropertyListeners(id, "link");
  }
}

function attachPropertyListeners(id, type) {
  const lblInput = document.getElementById("propLabel");
  if (lblInput) {
    lblInput.addEventListener("input", e => {
      pushHistory();
      if (type === "node") {
        state.nodes[id].label = e.target.value;
      } else {
        state.links[id].params.label = e.target.value;
      }
      state.hasResults = false;
      renderAll();
    });
  }
  
  const btnDelete = document.getElementById("btnDeleteSelectedProp");
  if (btnDelete) {
    btnDelete.addEventListener("click", deleteSelected);
  }
  
  if (type === "node") {
    const xInput = document.getElementById("propX");
    const yInput = document.getElementById("propY");
    
    const updatePos = () => {
      pushHistory();
      state.nodes[id].x = Number(xInput.value);
      state.nodes[id].y = Number(yInput.value);
      state.hasResults = false;
      renderAll();
    };
    
    if (xInput) xInput.addEventListener("change", updatePos);
    if (yInput) yInput.addEventListener("change", updatePos);
    
    // Node params
    ["vn_kv", "vm_pu", "va_degree", "p_mw", "q_mvar", "sn_mva", "vn_hv_kv", "vn_lv_kv", "vk_percent", "vkr_percent"].forEach(field => {
      const input = document.getElementById(`param_${field}`);
      if (input) {
        input.addEventListener("change", e => {
          pushHistory();
          state.nodes[id].params[field] = Number(e.target.value);
          state.hasResults = false;
          renderAll();
        });
      }
    });
  } else {
    // Link params
    ["length_km", "r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km", "max_i_ka"].forEach(field => {
      const input = document.getElementById(`line_${field}`);
      if (input) {
        input.addEventListener("change", e => {
          pushHistory();
          state.links[id].params[field] = Number(e.target.value);
          state.hasResults = false;
          renderAll();
        });
      }
    });
  }
}

// -------------------------------------------------------------
// Import / Export
// -------------------------------------------------------------
function saveProject() {
  const payload = {
    nodes: state.nodes,
    links: state.links,
    nextId: state.nextId
  };
  localStorage.setItem("grid-simulator-project", JSON.stringify(payload));
  showStatus("Project disimpan ke LocalStorage", "ok");
}

function loadProject() {
  const raw = localStorage.getItem("grid-simulator-project");
  if (!raw) {
    showStatus("Tidak ada data tersimpan", "warn");
    return;
  }
  pushHistory();
  const payload = JSON.parse(raw);
  state.nodes = payload.nodes || {};
  state.links = payload.links || {};
  state.nextId = normalizeNextId(payload.nextId);
  state.selectedId = null;
  state.selectedType = null;
  state.hasResults = false;
  
  showStatus("Project dimuat dari LocalStorage", "ok");
  renderAll();
  renderProperties();
  fitCanvas();
}

function exportResults() {
  const payload = {
    nodes: state.nodes,
    links: state.links,
    results: state.results,
    hasResults: state.hasResults
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `grid_project_${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showStatus("Hasil berhasil diekspor", "ok");
}

function setButtonLabel(button, text) {
  const label = button.querySelector("span");
  if (label) {
    label.textContent = text;
  } else {
    button.textContent = text;
  }
}

// -------------------------------------------------------------
// Event Listeners Binding
// -------------------------------------------------------------
function setupEventListeners() {
  // Sidebar toggles
  const shell = document.querySelector(".app-shell");
  const btnToggleLeft = document.getElementById("btnToggleLeft");
  const btnToggleRight = document.getElementById("btnToggleRight");
  
  btnToggleLeft.addEventListener("click", () => {
    shell.classList.toggle("hide-left");
    const hidden = shell.classList.contains("hide-left");
    setButtonLabel(btnToggleLeft, hidden ? "Show Panel" : "Hide Panel");
    btnToggleLeft.classList.toggle("active", hidden);
  });
  
  btnToggleRight.addEventListener("click", () => {
    shell.classList.toggle("hide-right");
    const hidden = shell.classList.contains("hide-right");
    setButtonLabel(btnToggleRight, hidden ? "Show Props" : "Hide Props");
    btnToggleRight.classList.toggle("active", hidden);
  });

  // Navigation buttons
  document.getElementById("btnUndo").addEventListener("click", undo);
  document.getElementById("btnRedo").addEventListener("click", redo);
  document.getElementById("btnDelete").addEventListener("click", deleteSelected);
  document.getElementById("btnZoomOut").addEventListener("click", zoomOut);
  document.getElementById("btnZoomIn").addEventListener("click", zoomIn);
  document.getElementById("btnZoomReset").addEventListener("click", zoomReset);
  document.getElementById("btnFit").addEventListener("click", fitCanvas);
  
  // Toolbar additions
  document.querySelectorAll("[data-add]").forEach(btn => {
    btn.addEventListener("click", () => addComponent(btn.dataset.add));
  });
  
  // Simulation triggers
  document.getElementById("btnRun").addEventListener("click", runPowerFlowSimulation);
  document.getElementById("btnRunSide").addEventListener("click", runPowerFlowSimulation);
  document.getElementById("btnValidate").addEventListener("click", validateNetwork);
  document.getElementById("btnValidateTop").addEventListener("click", validateNetwork);
  
  // Project files
  document.getElementById("btnNew").addEventListener("click", newProject);
  document.getElementById("btnTemplate").addEventListener("click", loadTemplate);
  document.getElementById("btnSave").addEventListener("click", saveProject);
  document.getElementById("btnLoad").addEventListener("click", loadProject);
  document.getElementById("btnExport").addEventListener("click", exportResults);

  const actionHandlers = {
    new: newProject,
    template: loadTemplate,
    save: saveProject,
    load: loadProject,
    export: exportResults,
    undo,
    redo,
    delete: deleteSelected,
    "toggle-left": () => btnToggleLeft.click(),
    "toggle-right": () => btnToggleRight.click(),
    "zoom-in": zoomIn,
    "zoom-out": zoomOut,
    "zoom-reset": zoomReset,
    "zoom-fit": fitCanvas,
  };

  document.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", () => {
      const handler = actionHandlers[btn.dataset.action];
      if (handler) handler();
    });
  });
  
  // Viewport interactions
  viewport.addEventListener("wheel", handleZoom);
  viewport.addEventListener("mousedown", handleMouseDown);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUp);
  
  // Segmented modes
  const modeRigid = document.getElementById("modeRigid");
  const modeResults = document.getElementById("modeResults");
  
  modeRigid.addEventListener("click", () => {
    modeRigid.classList.add("active");
    modeResults.classList.remove("active");
    // Show standard diagram view
  });
  
  modeResults.addEventListener("click", () => {
    modeResults.classList.add("active");
    modeRigid.classList.remove("active");
    if (!state.hasResults) runPowerFlowSimulation();
  });
  
  // Keyboard Hotkeys
  document.addEventListener("keydown", event => {
    const activeEl = document.activeElement;
    if (activeEl && ["INPUT", "SELECT", "TEXTAREA"].includes(activeEl.tagName)) {
      return; // Skip when typing in fields
    }
    
    // Ctrl + Z = Undo
    if (event.ctrlKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      undo();
    }
    // Ctrl + Y = Redo
    if (event.ctrlKey && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redo();
    }
    // Del / Backspace = Delete selected
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      deleteSelected();
    }
  });
}

// -------------------------------------------------------------
// Initialize App
// -------------------------------------------------------------
setupEventListeners();
loadTemplate(); // Load default template on start
setTimeout(fitCanvas, 200);
