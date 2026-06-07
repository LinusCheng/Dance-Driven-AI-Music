const BACKEND_URL = 'ws://localhost:8765';
const RECONNECT_DELAY_MS = 3000;
const SEND_INTERVAL_MS = 250;

export function createBackendClient(ui) {
  let socket = null;
  let reconnectTimer = null;
  let sendTimer = null;
  let latestMovementData = null;
  let backendDebugEnabled = false;
  let magentaMotionInputEnabled = false;
  let magentaModelSize = 'small';
  let liveControls = {
    temperature: 1.0,
  };
  let manualPrompt = '';
  let manualClose = false;

  function setStatus(text, connected = false) {
    if (ui?.setBackendStatus) {
      ui.setBackendStatus(text, connected);
    }
  }

  function cleanupSocket() {
    if (socket) {
      socket.onopen = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.close();
      socket = null;
    }
  }

  function scheduleReconnect() {
    if (manualClose || reconnectTimer) {
      return;
    }

    setStatus('GenMusicHub disconnected', false);
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, RECONNECT_DELAY_MS);
  }

  function connect() {
    cleanupSocket();

    try {
      setStatus('GenMusicHub connecting...', false);
      socket = new WebSocket(BACKEND_URL);
    } catch (error) {
      console.warn('WebSocket connect failed', error);
      scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      setStatus('GenMusicHub connected', true);
      sendBackendDebugPreference();
      sendMagentaMotionInputPreference();
      sendMagentaModelSizePreference();
      sendLiveControls();
      sendManualPrompt();
      console.info('GenMusicHub WebSocket connected.');
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type === 'backendDebug') {
          ui?.updateBackendDebug?.(message);
          return;
        }
        if (message?.type === 'backendDebugStatus') {
          ui?.setBackendDebugEnabled?.(Boolean(message.enabled));
          return;
        }
        if (message?.type === 'gestureAction') {
          ui?.showGestureAction?.(message.action);
          return;
        }
        if (message?.type === 'manualPromptStatus') {
          manualPrompt = String(message.prompt ?? '');
          ui?.setManualPromptStatus?.(manualPrompt);
          return;
        }
        if (message?.type === 'magentaMotionInputStatus') {
          magentaMotionInputEnabled = Boolean(message.enabled);
          ui?.setMagentaMotionInputEnabled?.(magentaMotionInputEnabled);
          return;
        }
        if (message?.type === 'magentaModelSizeStatus') {
          magentaModelSize = String(message.size || 'small');
          ui?.setMagentaModelSize?.(magentaModelSize, message.modelName);
          return;
        }
        if (message?.type === 'liveControlsStatus') {
          ui?.setLiveControlsStatus?.(message.controls, Boolean(message.applied));
          return;
        }
      } catch {
        // Ignore non-JSON backend messages; terminal logs stay out of the UI.
      }

      console.debug('GenMusicHub emitted:', event.data);
    };

    socket.onerror = () => {
      console.warn('GenMusicHub WebSocket error.');
      scheduleReconnect();
    };

    socket.onclose = () => {
      console.info('GenMusicHub WebSocket closed.');
      scheduleReconnect();
    };
  }

  function sendMovementData() {
    if (!socket || socket.readyState !== WebSocket.OPEN || !latestMovementData) {
      return;
    }

    try {
      const payload = {
        ...latestMovementData,
        timestamp: Date.now(),
      };
      socket.send(JSON.stringify(payload));
    } catch (error) {
      console.warn('Failed to send backend payload:', error);
    }
  }

  function sendBackendDebugPreference() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({
      type: 'setBackendDebug',
      enabled: backendDebugEnabled,
    }));
  }

  function sendManualPrompt() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({
      type: 'setManualPrompt',
      prompt: manualPrompt,
    }));
  }

  function sendMagentaMotionInputPreference() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({
      type: 'setMagentaMotionInput',
      enabled: magentaMotionInputEnabled,
    }));
  }

  function sendMagentaModelSizePreference() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({
      type: 'setMagentaModelSize',
      size: magentaModelSize,
    }));
  }

  function sendLiveControls() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }

    socket.send(JSON.stringify({
      type: 'setLiveControls',
      controls: liveControls,
    }));
  }

  function setManualPrompt(prompt) {
    manualPrompt = String(prompt ?? '').trim().slice(0, 280);
    ui?.setManualPromptStatus?.(manualPrompt);
    sendManualPrompt();
  }

  function setBackendDebugEnabled(enabled) {
    backendDebugEnabled = Boolean(enabled);
    ui?.setBackendDebugEnabled?.(backendDebugEnabled);
    sendBackendDebugPreference();
  }

  function toggleBackendDebug() {
    setBackendDebugEnabled(!backendDebugEnabled);
  }

  function setMagentaMotionInputEnabled(enabled) {
    magentaMotionInputEnabled = Boolean(enabled);
    ui?.setMagentaMotionInputEnabled?.(magentaMotionInputEnabled);
    sendMagentaMotionInputPreference();
  }

  function toggleMagentaMotionInput() {
    setMagentaMotionInputEnabled(!magentaMotionInputEnabled);
  }

  function setMagentaModelSize(size) {
    magentaModelSize = size === 'base' ? 'base' : 'small';
    ui?.setMagentaModelSize?.(magentaModelSize);
    sendMagentaModelSizePreference();
  }

  function toggleMagentaModelSize() {
    setMagentaModelSize(magentaModelSize === 'small' ? 'base' : 'small');
  }

  function setTemperature(value) {
    const number = Number(value);
    const temperature = Number.isFinite(number)
      ? Math.max(0.5, Math.min(2.0, number))
      : 1.0;
    liveControls = {
      ...liveControls,
      temperature,
    };
    ui?.setTemperature?.(temperature);
    sendLiveControls();
  }

  function startSendLoop() {
    if (sendTimer) {
      return;
    }

    sendTimer = window.setInterval(() => {
      sendMovementData();
    }, SEND_INTERVAL_MS);
  }

  function stopSendLoop() {
    if (sendTimer) {
      window.clearInterval(sendTimer);
      sendTimer = null;
    }
  }

  function dispose() {
    manualClose = true;
    stopSendLoop();
    cleanupSocket();
  }

  function updateMovementData(data) {
    latestMovementData = data;
  }

  connect();
  startSendLoop();
  ui?.setBackendDebugEnabled?.(backendDebugEnabled);
  ui?.setMagentaMotionInputEnabled?.(magentaMotionInputEnabled);
  ui?.setMagentaModelSize?.(magentaModelSize);
  ui?.setTemperature?.(liveControls.temperature);

  return {
    updateMovementData,
    toggleBackendDebug,
    setBackendDebugEnabled,
    toggleMagentaMotionInput,
    setMagentaMotionInputEnabled,
    toggleMagentaModelSize,
    setMagentaModelSize,
    setTemperature,
    setManualPrompt,
    dispose,
  };
}
