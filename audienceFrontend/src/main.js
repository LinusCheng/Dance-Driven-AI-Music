import './style.css';

const BACKEND_URL = 'ws://localhost:8765';

const defaultNodes = [
  { id: 'node_1', label: 'Anchor', prompt: 'Harold bud style', weight: 1, enabled: true },
  { id: 'node_2', label: 'Groove', prompt: 'laurie spiegel', weight: 0.5, enabled: false },
  { id: 'node_3', label: 'Space', prompt: 'ambient gamelan', weight: 0.5, enabled: false },
  // Re-enable these when you want the full six-node prompt surface again.
  // { id: 'node_4', label: 'Drive', prompt: 'driving techno industrial pulse', weight: 0.5, enabled: false },
  // { id: 'node_5', label: 'Drama', prompt: 'cinematic experimental motion', weight: 0.5, enabled: false },
  // { id: 'node_6', label: 'Funk', prompt: 'funky syncopated bass and drums', weight: 0.5, enabled: false },
];

const state = {
  socket: null,
  connected: false,
  status: 'Disconnected',
  lastEngine: null,
  nodes: structuredClone(defaultNodes),
  reconnectTimer: null,
};

const app = document.querySelector('#app');

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function nodeById(id) {
  return state.nodes.find((node) => node.id === id);
}

function outgoingWeights() {
  const weights = {};
  for (const node of state.nodes) {
    weights[node.id] = node.enabled ? clamp(Number(node.weight) || 0, 0, 1) : 0;
  }
  return weights;
}

function totalWeight() {
  return Object.values(outgoingWeights()).reduce((sum, weight) => sum + weight, 0);
}

function setStatus(status) {
  state.status = status;
  document.querySelector('[data-status]')?.replaceChildren(document.createTextNode(status));
}

function updateTotal() {
  const total = document.querySelector('[data-total]');
  if (total) {
    total.textContent = totalWeight().toFixed(2);
  }
}

function updateNodeDisplay(node) {
  const card = document.querySelector(`[data-card="${node.id}"]`);
  if (!card) return;

  const percent = Math.round((node.enabled ? Number(node.weight) || 0 : 0) * 100);
  card.classList.toggle('is-off', !node.enabled);
  card.querySelector('[data-output]')?.replaceChildren(document.createTextNode(`${percent}%`));
  card.querySelector('[data-toggle]')?.replaceChildren(document.createTextNode(node.enabled ? 'On' : 'Off'));
  card.querySelector('[data-prompt]')?.replaceChildren(document.createTextNode(node.prompt || ''));
  const slider = card.querySelector('[data-field="weight"]');
  if (slider && Number(slider.value) !== Number(node.weight)) {
    slider.value = String(node.weight);
  }
  updateTotal();
}

function updateAllNodeDisplays() {
  for (const node of state.nodes) {
    updateNodeDisplay(node);
  }
}

function updatePromptTexts(promptTexts) {
  if (!promptTexts || typeof promptTexts !== 'object') {
    return;
  }
  for (const node of state.nodes) {
    if (promptTexts[node.id] !== undefined) {
      node.prompt = String(promptTexts[node.id] || '');
      updateNodeDisplay(node);
    }
  }
}

function updateEngineStatus() {
  const engine = state.lastEngine || {};
  const controls = engine.controls || {};
  const entries = {
    model: engine.modelName || '--',
    audio: engine.audioReady === undefined ? '--' : String(engine.audioReady),
    buffer: engine.runnerBufferAvailable === undefined ? '--' : `${engine.runnerBufferAvailable}/${engine.runnerBufferCapacity || '--'}`,
    underruns: engine.audioUnderruns ?? '--',
    peak: engine.audioPeak === undefined ? '--' : Number(engine.audioPeak).toFixed(3),
    temp: controls.temperature ?? '--',
    topk: controls.top_k ?? '--',
  };

  for (const [key, value] of Object.entries(entries)) {
    const target = document.querySelector(`[data-engine="${key}"]`);
    if (target) {
      target.textContent = value;
    }
  }
}

function sendPromptWeights() {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    setStatus('Backend is not connected');
    return;
  }

  state.socket.send(JSON.stringify({
    type: 'setPromptWeights',
    weights: outgoingWeights(),
  }));
  setStatus('Weights submitted');
}

function scheduleReconnect() {
  if (state.reconnectTimer || state.connected) {
    return;
  }
  state.reconnectTimer = window.setTimeout(() => {
    state.reconnectTimer = null;
    connect(true);
  }, 1600);
}

function connect(isRetry = false) {
  if (state.socket && state.socket.readyState === WebSocket.OPEN) {
    return;
  }
  if (state.socket && state.socket.readyState === WebSocket.CONNECTING) {
    return;
  }

  setStatus(isRetry ? 'Retrying backend...' : 'Connecting...');
  const socket = new WebSocket(BACKEND_URL);
  state.socket = socket;

  socket.addEventListener('open', () => {
    if (state.reconnectTimer) {
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
    state.connected = true;
    document.querySelector('.connection')?.classList.add('is-on');
    setStatus('Connected');
    socket.send(JSON.stringify({ type: 'setBackendDebug', enabled: true }));
  });

  socket.addEventListener('message', (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    if (payload.type === 'promptWeightsStatus') {
      for (const node of state.nodes) {
        if (payload.weights?.[node.id] !== undefined) {
          const incomingWeight = Number(payload.weights[node.id]) || 0;
          node.enabled = incomingWeight > 0;
          node.weight = incomingWeight > 0 ? incomingWeight : node.weight;
        }
      }
      setStatus('Weights applied');
      updateAllNodeDisplays();
    }

    if (payload.type === 'backendDebug') {
      state.lastEngine = payload.engine?.lastResponse || payload.engine || payload;
      updatePromptTexts(payload.settings?.promptTexts);
      updateEngineStatus();
    }
  });

  socket.addEventListener('close', () => {
    state.connected = false;
    document.querySelector('.connection')?.classList.remove('is-on');
    setStatus(`Disconnected from ${BACKEND_URL}`);
    scheduleReconnect();
  });

  socket.addEventListener('error', () => {
    state.connected = false;
    document.querySelector('.connection')?.classList.remove('is-on');
    setStatus(`Connection error: ${BACKEND_URL}`);
    scheduleReconnect();
  });
}

function resetNodes() {
  state.nodes = structuredClone(defaultNodes);
  updateAllNodeDisplays();
  sendPromptWeights();
}

function renderEngineStatus() {
  const entries = [
    ['model', 'Model'],
    ['audio', 'Audio'],
    ['buffer', 'Buffer'],
    ['underruns', 'Underruns'],
    ['peak', 'Peak'],
    ['temp', 'Temp'],
    ['topk', 'Top K'],
  ];

  return `
    <section class="status-grid" aria-label="Engine status">
      ${entries.map(([key, label]) => `
        <div class="status-cell">
          <span>${escapeHtml(label)}</span>
          <strong data-engine="${key}">--</strong>
        </div>
      `).join('')}
    </section>
  `;
}

function renderNode(node) {
  const percent = Math.round((node.enabled ? Number(node.weight) || 0 : 0) * 100);
  return `
    <article class="prompt-card ${node.enabled ? '' : 'is-off'}" data-card="${node.id}">
      <header>
        <div>
          <span class="node-id">${escapeHtml(node.id)}</span>
          <h2>${escapeHtml(node.label)}</h2>
        </div>
        <div class="node-actions">
          <output data-output>${percent}%</output>
          <button class="toggle-button" data-toggle data-node="${node.id}" type="button">${node.enabled ? 'On' : 'Off'}</button>
        </div>
      </header>
      <p class="prompt-text" data-prompt>${escapeHtml(node.prompt || '')}</p>
      <input
        data-node="${node.id}"
        data-field="weight"
        type="range"
        min="0"
        max="1"
        step="0.01"
        value="${node.weight}"
        aria-label="${escapeHtml(node.label)} weight"
      />
    </article>
  `;
}

function bindEvents() {
  document.querySelector('#connectButton')?.addEventListener('click', connect);
  document.querySelector('#sendButton')?.addEventListener('click', sendPromptWeights);
  document.querySelector('#resetButton')?.addEventListener('click', resetNodes);

  document.querySelectorAll('[data-toggle]').forEach((button) => {
    button.addEventListener('click', (event) => {
      const node = nodeById(event.currentTarget.dataset.node);
      if (!node) return;
      node.enabled = !node.enabled;
      if (node.enabled && Number(node.weight) <= 0) {
        node.weight = 0.5;
      }
      updateNodeDisplay(node);
    });
  });

  document.querySelectorAll('[data-field="weight"]').forEach((input) => {
    input.addEventListener('input', (event) => {
      const node = nodeById(event.currentTarget.dataset.node);
      if (!node) return;
      node.weight = Number(event.currentTarget.value);
      if (node.weight > 0) {
        node.enabled = true;
      }
      updateNodeDisplay(node);
    });
  });
}

function render() {
  app.innerHTML = `
    <section class="shell">
      <header class="topbar">
        <div>
          <p class="eyebrow">Audience Frontend</p>
          <h1>Prompt Blend</h1>
        </div>
        <div class="connection ${state.connected ? 'is-on' : ''}">
          <span></span>
          <strong data-status>${escapeHtml(state.status)}</strong>
        </div>
      </header>

      ${renderEngineStatus()}

      <section class="toolbar" aria-label="Prompt actions">
        <button id="connectButton" type="button">${state.connected ? 'Reconnect' : 'Connect'}</button>
        <button id="sendButton" type="button">Submit Weights</button>
        <button id="resetButton" type="button">Reset</button>
        <div class="total">
          <span>Total Weight</span>
          <strong data-total>${totalWeight().toFixed(2)}</strong>
        </div>
      </section>

      <section class="prompt-grid" aria-label="Prompt nodes">
        ${state.nodes.map(renderNode).join('')}
      </section>
    </section>
  `;
  bindEvents();
  updateEngineStatus();
}

render();
connect();
