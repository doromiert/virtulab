const rack = document.querySelector('#rack');
const layer = document.querySelector('#cable-layer');
const preview = document.querySelector('#preview-cable');
const toast = document.querySelector('#toast');
const saveState = document.querySelector('#save-state');
const dialog = document.querySelector('#confirm-dialog');
const setupDialog = document.querySelector('#setup-dialog');
const setupModeDialog = document.querySelector('#setup-mode-dialog');

let state = null;
let connections = [];
let selectedColor = 'yellow';
let selectedCable = null;
let drag = null;
let dirty = false;
let lastSetupPhase = null;
let lastRecoveryPhase = null;

const cableColors = {
  yellow: '#f4c430', blue: '#3488db', red: '#dc4641', green: '#4ea85c', black: '#25282a'
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: options.body === undefined && options.method && options.method !== 'GET' ? '{}' : options.body
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Błąd żądania (${response.status})`);
  return data;
}

function notify(message, error = false) {
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.classList.add('show');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('show'), 3500);
}

function endpointCenter(endpoint) {
  const port = document.querySelector(`[data-endpoint="${endpoint}"] .socket`);
  const a = port.getBoundingClientRect();
  const b = rack.getBoundingClientRect();
  return { x: a.left + a.width / 2 - b.left, y: a.top + a.height / 2 - b.top };
}

function curve(a, b) {
  const slack = Math.max(75, Math.abs(b.y - a.y) * .38 + Math.abs(b.x - a.x) * .13);
  const low = Math.max(a.y, b.y) + slack;
  return `M ${a.x} ${a.y} C ${a.x} ${low}, ${b.x} ${low}, ${b.x} ${b.y}`;
}

function svgElement(name, attributes) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function drawCables() {
  layer.replaceChildren();
  document.querySelectorAll('.port').forEach(port => {
    port.classList.remove('connected');
    port.style.removeProperty('--cable-color');
  });
  connections.forEach(cable => {
    const a = endpointCenter(cable.a);
    const b = endpointCenter(cable.b);
    const d = curve(a, b);
    const group = svgElement('g', { 'data-cable': cable.id });
    const hit = svgElement('path', { d, class: 'cable-hit' });
    const body = svgElement('path', { d, class: `cable${selectedCable === cable.id ? ' selected' : ''}`, stroke: cableColors[cable.color] });
    const shine = svgElement('path', { d, class: 'cable-highlight' });
    const plugA = svgElement('rect', { x: a.x - 9, y: a.y - 8, width: 18, height: 16, class: 'plug', fill: cableColors[cable.color] });
    const plugB = svgElement('rect', { x: b.x - 9, y: b.y - 8, width: 18, height: 16, class: 'plug', fill: cableColors[cable.color] });
    hit.addEventListener('pointerdown', event => {
      event.stopPropagation();
      selectedCable = cable.id;
      drawCables();
    });
    group.append(hit, body, shine, plugA, plugB);
    layer.append(group);
    [cable.a, cable.b].forEach(endpoint => {
      const port = document.querySelector(`[data-endpoint="${endpoint}"]`);
      port.classList.add('connected');
      port.style.setProperty('--cable-color', cableColors[cable.color]);
    });
  });
}

function setDirty(value) {
  dirty = value;
  saveState.textContent = value ? 'Topologia niezastosowana' : 'Topologia zsynchronizowana';
  document.querySelector('#apply').disabled = !value;
}

function portAt(x, y) {
  for (const element of document.elementsFromPoint(x, y)) {
    const port = element.closest?.('.port');
    if (port) return port;
  }
  return null;
}

async function persistTopology() {
  await api('/api/topology', { method: 'PUT', body: JSON.stringify({ connections }) });
  setDirty(true);
  const result = await api('/api/apply', { method: 'POST' });
  setDirty(false);
  notify(result.message);
}

function startCable(event) {
  const port = event.currentTarget;
  const endpoint = port.dataset.endpoint;
  const existing = connections.find(cable => cable.a === endpoint || cable.b === endpoint);
  event.preventDefault();
  if (existing) {
    const anchor = existing.a === endpoint ? existing.b : existing.a;
    connections = connections.filter(cable => cable.id !== existing.id);
    drag = {
      endpoint: anchor,
      start: endpointCenter(anchor),
      pointerId: event.pointerId,
      original: existing
    };
    port.setPointerCapture(event.pointerId);
    preview.style.stroke = cableColors[existing.color];
    preview.removeAttribute('hidden');
    selectedCable = null;
    drawCables();
    return;
  }
  drag = { endpoint, start: endpointCenter(endpoint), pointerId: event.pointerId };
  port.setPointerCapture(event.pointerId);
  preview.style.stroke = cableColors[selectedColor];
  preview.removeAttribute('hidden');
}

function moveCable(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  const bounds = rack.getBoundingClientRect();
  preview.setAttribute('d', curve(drag.start, { x: event.clientX - bounds.left, y: event.clientY - bounds.top }));
  document.querySelectorAll('.port.drag-target').forEach(port => port.classList.remove('drag-target'));
  const target = portAt(event.clientX, event.clientY);
  if (target && target.dataset.endpoint !== drag.endpoint) target.classList.add('drag-target');
}

function clearCablePreview() {
  preview.setAttribute('hidden', '');
  preview.setAttribute('d', '');
  document.querySelectorAll('.port.drag-target').forEach(port => port.classList.remove('drag-target'));
}

async function finishCable(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  const source = drag.endpoint;
  const original = drag.original;
  drag = null;
  clearCablePreview();
  const target = portAt(event.clientX, event.clientY);
  if (!target) {
    drawCables();
    if (original) {
      try { await persistTopology(); } catch (error) { notify(error.message, true); await refresh(); }
    }
    return;
  }
  if (target.dataset.endpoint === source) {
    if (original) connections.push(original);
    drawCables();
    return;
  }
  connections = connections.filter(cable =>
    cable.a !== source && cable.b !== source &&
    cable.a !== target.dataset.endpoint && cable.b !== target.dataset.endpoint
  );
  connections.push({
    id: original?.id || crypto.randomUUID().slice(0, 12),
    a: source,
    b: target.dataset.endpoint,
    color: original?.color || selectedColor
  });
  selectedCable = null;
  drawCables();
  try { await persistTopology(); } catch (error) { notify(error.message, true); await refresh(); }
}

function cancelCable(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (drag.original) connections.push(drag.original);
  drag = null;
  clearCablePreview();
  drawCables();
}

function deviceControls(vm, status) {
  const client = state.clients[vm];
  const running = status === 'running';
  const recoveryRunning = state.recovery?.phase === 'running';
  const resetUnavailable = recoveryRunning || running || (client && !client.runtime);
  const promoteUnavailable = recoveryRunning || !client || !client.runtime || Object.entries(state.vms)
    .some(([name, vmState]) => name.startsWith('client') && !['shut off', 'undefined'].includes(vmState));
  const statusLabel = {
    running: 'uruchomiona',
    'shut off': 'wyłączona',
    undefined: 'nieutworzona',
    paused: 'wstrzymana'
  }[status] || status;
  return `
    <span class="state ${running ? 'running' : ''}">${statusLabel}</span>
    <button class="icon-button" data-action="console" title="Otwórz konsolę" aria-label="Otwórz konsolę" ${recoveryRunning ? 'disabled' : ''}><i data-lucide="monitor"></i></button>
    <button class="icon-button" data-action="${running ? 'shutdown' : 'start'}" title="${running ? 'Wyłącz maszynę (Shift: wymuś)' : 'Uruchom maszynę'}" aria-label="${running ? 'Wyłącz maszynę; Shift wymusza zatrzymanie' : 'Uruchom maszynę'}" ${recoveryRunning ? 'disabled' : ''}><i data-lucide="${running ? 'power' : 'play'}"></i></button>
    ${client ? `<button class="icon-button" data-action="promote" title="Ustaw jako obraz odzyskiwania" aria-label="Ustaw jako obraz odzyskiwania" ${promoteUnavailable ? 'disabled' : ''}><i data-lucide="archive-restore"></i></button>` : ''}
    <button class="icon-button danger" data-action="reset" title="Przywróć stan bazowy" aria-label="Przywróć stan bazowy" ${resetUnavailable ? 'disabled' : ''}><i data-lucide="rotate-ccw"></i></button>`;
}

function renderStatus() {
  document.querySelector('#host-status').textContent = state.libvirtUri;
  document.querySelector('#host-dot').classList.toggle('ok', state.prepared);
  for (const [vm, status] of Object.entries(state.vms)) {
    const controls = document.querySelector(`[data-vm="${vm}"] .device-controls`);
    controls.innerHTML = deviceControls(vm, status);
    controls.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', event => {
      let action = button.dataset.action;
      if (action === 'shutdown' && event.shiftKey) action = 'force-stop';
      vmAction(vm, action);
    }));
    const light = document.querySelector(`[data-vm="${vm}"] .power-light`);
    if (light) light.style.background = status === 'running' ? '#76d34d' : '#768087';
  }
  window.lucide?.createIcons({ attrs: { 'aria-hidden': 'true', 'stroke-width': 2 } });
}

async function vmAction(vm, action) {
  if (action === 'reset') {
    const name = vm === 'router' ? 'router' : `klienta ${vm.slice(-1)}`;
    document.querySelector('#dialog-title').textContent = `Przywrócić ${name}?`;
    document.querySelector('#dialog-copy').textContent = 'Dysk roboczy zostanie usunięty i odtworzony z czystego stanu bazowego. Tej operacji nie można cofnąć.';
    dialog.showModal();
    if (await new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true })) === false) return;
  } else if (action === 'promote') {
    document.querySelector('#dialog-title').textContent = `Zaktualizować obraz z klienta ${vm.slice(-1)}?`;
    document.querySelector('#dialog-copy').textContent = 'Bieżący dysk tego klienta zastąpi wspólny obraz odzyskiwania. Oba klienty zostaną natychmiast zresetowane do nowego obrazu. Tej operacji nie można cofnąć.';
    dialog.querySelector('button[value="confirm"]').textContent = 'Zaktualizuj obraz';
    dialog.showModal();
    const confirmed = await new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true }));
    dialog.querySelector('button[value="confirm"]').textContent = 'Przywróć maszynę';
    if (!confirmed) return;
  }
  try {
    const result = await api(`/api/vm/${vm}/${action}`, { method: 'POST' });
    notify(result.message);
    setTimeout(refresh, action === 'shutdown' ? 1200 : 250);
  } catch (error) { notify(error.message, true); }
}

async function refresh() {
  try {
    state = await api('/api/state');
    if (!drag) connections = state.topology.connections;
    renderStatus();
    if (!drag) drawCables();
    setDirty(!state.topologyApplied);
    if (state.recovery?.phase === 'running') {
      saveState.textContent = `Aktualizacja obrazu: ${state.recovery.progress.toFixed(1)}%`;
    } else if (state.recovery?.phase === 'complete' && lastRecoveryPhase !== 'complete') {
      notify(state.recovery.message);
    } else if (state.recovery?.phase === 'error' && lastRecoveryPhase !== 'error') {
      notify(state.recovery.message, true);
    }
    lastRecoveryPhase = state.recovery?.phase;
  } catch (error) { notify(error.message, true); }
}

function formatBytes(value) {
  if (!value) return '';
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
}

async function refreshSetupStatus() {
  try {
    const status = await api('/api/setup/status');
    const active = !['idle', 'error', 'complete', 'waiting-local'].includes(status.phase);
    const progress = document.querySelector('#setup-progress');
    progress.hidden = status.phase === 'idle';
    const percent = status.total ? Math.min(100, status.downloaded / status.total * 100) : 0;
    document.querySelector('#setup-progress-bar').style.width = `${percent}%`;
    const phaseLabels = {
      idle: 'Gotowy', resolving: 'Microsoft', downloading: 'Pobieranie',
      preparing: 'Przygotowanie', 'template-running': 'Konfiguracja Windows',
      'ready-to-seal': 'Gotowy do zapisu', sealing: 'Zapisywanie',
      'waiting-local': 'Pobieranie w przeglądarce', complete: 'Gotowe', error: 'Błąd'
    };
    document.querySelector('#setup-phase').textContent = phaseLabels[status.phase] || status.phase;
    document.querySelector('#setup-message').textContent = status.message;
    document.querySelector('#setup-bytes').textContent = status.total
      ? `${formatBytes(status.downloaded)} / ${formatBytes(status.total)}` : '';
    document.querySelector('#start-web-setup').hidden = active || status.phase === 'complete';
    document.querySelector('#start-web-setup').disabled = active;
    document.querySelector('#start-local-setup').disabled = active || status.phase === 'complete';
    const candidates = document.querySelector('#iso-candidates');
    candidates.replaceChildren(...(status.isoCandidates || []).map(path => {
      const option = document.createElement('option');
      option.value = path;
      return option;
    }));
    const localPath = document.querySelector('#existing-iso-path');
    if (!localPath.value && status.isoCandidates?.length) localPath.value = status.isoCandidates[0];
    document.querySelector('#open-template-console').hidden = !['template-running', 'ready-to-seal'].includes(status.phase);
    document.querySelector('#seal-template').hidden = status.phase !== 'ready-to-seal';
    if (status.phase === 'complete' && lastSetupPhase !== 'complete') {
      notify('Laboratorium jest gotowe');
      await refresh();
    }
    lastSetupPhase = status.phase;
  } catch (error) { notify(error.message, true); }
}

document.querySelectorAll('.port').forEach(port => {
  port.addEventListener('pointerdown', startCable);
});
document.addEventListener('pointermove', moveCable);
document.addEventListener('pointerup', finishCable);
document.addEventListener('pointercancel', cancelCable);
document.querySelectorAll('.swatch').forEach(swatch => swatch.addEventListener('click', async () => {
  selectedColor = swatch.dataset.color;
  document.querySelectorAll('.swatch').forEach(item => item.classList.toggle('selected', item === swatch));
  if (!selectedCable) return;
  const cable = connections.find(item => item.id === selectedCable);
  if (!cable || cable.color === selectedColor) return;
  cable.color = selectedColor;
  drawCables();
  try { await persistTopology(); } catch (error) { notify(error.message, true); await refresh(); }
}));
document.querySelector('#apply').addEventListener('click', async () => {
  try {
    const result = await api('/api/apply', { method: 'POST' });
    setDirty(false);
    notify(result.message);
    await refresh();
  } catch (error) { notify(error.message, true); }
});
document.querySelector('#setup-help').addEventListener('click', () => setupDialog.showModal());
document.querySelector('#close-setup').addEventListener('click', () => setupDialog.close());
document.querySelector('#setup-mode').addEventListener('click', () => {
  setupModeDialog.showModal();
  refreshSetupStatus();
});
document.querySelector('#close-setup-mode').addEventListener('click', () => setupModeDialog.close());
document.querySelector('#start-web-setup').addEventListener('click', async () => {
  try {
    await api('/api/setup/start', {
      method: 'POST',
      body: JSON.stringify({
        language: document.querySelector('#windows-language').value,
        source: document.querySelector('input[name="download-source"]:checked').value
      })
    });
    document.querySelector('#setup-progress').hidden = false;
    await refreshSetupStatus();
  } catch (error) { notify(error.message, true); }
});
document.querySelector('#start-local-setup').addEventListener('click', async () => {
  try {
    await api('/api/setup/start-local', {
      method: 'POST',
      body: JSON.stringify({ path: document.querySelector('#existing-iso-path').value })
    });
    document.querySelector('#setup-progress').hidden = false;
    await refreshSetupStatus();
  } catch (error) { notify(error.message, true); }
});
document.querySelectorAll('input[name="download-source"]').forEach(input => input.addEventListener('change', event => {
  const source = event.currentTarget.value;
  const enabled = source !== 'microsoft';
  const language = document.querySelector('#windows-language');
  if (enabled) language.value = 'Polish';
  language.disabled = enabled;
  const warning = document.querySelector('#mirror-warning');
  warning.hidden = !enabled;
  warning.textContent = source === 'massgrave'
    ? 'Massgrave otworzy interaktywny mirror ZeroFS w przeglądarce. Po pobraniu wskaż plik w polu istniejącego ISO.'
    : source === 'ntriver'
      ? 'NTriver pobiera z niezależnego mirroru. Setup wymusi zgodność rozmiaru i SHA-256 z katalogiem Massgrave/MVS.'
      : '';
  const labels = {
    microsoft: 'Pobierz i rozpocznij',
    massgrave: 'Otwórz Massgrave',
    ntriver: 'Pobierz przez NTriver'
  };
  document.querySelector('#start-web-setup span').textContent = labels[source];
}));
document.querySelector('#open-template-console').addEventListener('click', async () => {
  try { await api('/api/setup/console', { method: 'POST' }); }
  catch (error) { notify(error.message, true); }
});
document.querySelector('#seal-template').addEventListener('click', async () => {
  try {
    await api('/api/setup/seal', { method: 'POST' });
    await refreshSetupStatus();
  } catch (error) { notify(error.message, true); }
});
document.querySelectorAll('[data-setup-tab]').forEach(tab => tab.addEventListener('click', () => {
  const selected = tab.dataset.setupTab;
  document.querySelectorAll('[data-setup-tab]').forEach(item => {
    const active = item.dataset.setupTab === selected;
    item.classList.toggle('active', active);
    item.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-setup-panel]').forEach(panel => {
    panel.hidden = panel.dataset.setupPanel !== selected;
  });
}));
document.querySelectorAll('.copy-command').forEach(button => button.addEventListener('click', async () => {
  const command = button.closest('.command-block').querySelector('code').textContent.trim();
  try {
    await navigator.clipboard.writeText(command);
    notify('Skopiowano do schowka');
  } catch {
    notify('Nie udało się skopiować do schowka', true);
  }
}));
document.addEventListener('keydown', async event => {
  if ((event.key === 'Delete' || event.key === 'Backspace') && selectedCable && !dialog.open) {
    event.preventDefault();
    connections = connections.filter(cable => cable.id !== selectedCable);
    selectedCable = null;
    drawCables();
    try { await persistTopology(); } catch (error) { notify(error.message, true); }
  }
});
window.addEventListener('resize', drawCables);
rack.addEventListener('pointerdown', event => { if (event.target === rack) { selectedCable = null; drawCables(); } });
refresh();
setInterval(refresh, 5000);
setInterval(() => { if (setupModeDialog.open) refreshSetupStatus(); }, 1500);
