const SUNO_HUB_HTTP_URL = 'http://localhost:8000';
const SUNO_HUB_WS_URL = 'ws://localhost:8000/ws/suno';

function toSunoUrl(url) {
  if (!url) {
    return '';
  }

  try {
    return new URL(url, SUNO_HUB_HTTP_URL).href;
  } catch {
    return url;
  }
}

function setAudioSource(audio, url) {
  if (!audio || !url) {
    return;
  }

  audio.src = toSunoUrl(url);
  audio.load();
}

export function createSunoHubClient(root = document) {
  const status = root.getElementById('sunoStatus');
  const titleInput = root.getElementById('sunoTitleInput');
  const promptInput = root.getElementById('sunoPromptInput');
  const generateBtn = root.getElementById('sunoGenerateBtn');
  const previewAudio = root.getElementById('sunoPreviewAudio');
  const finalAudio = root.getElementById('sunoFinalAudio');
  const loopGrid = root.getElementById('sunoLoopGrid');

  let socket = null;
  let socketReady = null;

  function setStatus(text, tone = '') {
    if (!status) {
      return;
    }

    status.textContent = text;
    status.dataset.tone = tone;
  }

  function setBusy(isBusy) {
    if (generateBtn) {
      generateBtn.disabled = isBusy;
      generateBtn.textContent = isBusy ? 'Generating...' : 'Generate';
    }
  }

  function renderLoops(loops = []) {
    if (!loopGrid) {
      return;
    }

    loopGrid.innerHTML = '';
    loops.forEach((loop, index) => {
      const item = document.createElement('article');
      item.className = 'suno-loop-card';

      const label = document.createElement('span');
      label.textContent = `Loop ${index + 1}`;

      const meta = document.createElement('small');
      meta.textContent = loop.duration ? `${Number(loop.duration).toFixed(1)}s` : loop.name;

      const audio = document.createElement('audio');
      audio.controls = true;
      audio.loop = true;
      audio.src = toSunoUrl(loop.url);

      item.append(label, meta, audio);
      loopGrid.appendChild(item);
    });
  }

  async function connect() {
    if (socket?.readyState === WebSocket.OPEN) {
      return socket;
    }

    if (socketReady) {
      return socketReady;
    }

    socket = new WebSocket(SUNO_HUB_WS_URL);
    socketReady = new Promise((resolve, reject) => {
      socket.addEventListener('open', () => {
        setStatus('connected', 'ok');
        resolve(socket);
      }, { once: true });
      socket.addEventListener('error', () => {
        setBusy(false);
        setStatus('offline', 'warn');
        socketReady = null;
        reject(new Error('SunoHub is not running.'));
      }, { once: true });
    });

    socket.addEventListener('close', () => {
      setBusy(false);
      setStatus('offline', 'warn');
      socketReady = null;
    });

    socket.addEventListener('message', (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }

      if (payload.type === 'suno:submitted') {
        setStatus(payload.id ? `submitted ${payload.id}` : 'submitted', 'ok');
      } else if (payload.type === 'suno:status') {
        const error = payload.error ? `: ${payload.error}` : '';
        setStatus(`${payload.status || 'working'}${error}`, payload.status === 'error' ? 'warn' : '');
        if (payload.status === 'error') {
          setBusy(false);
        }
      } else if (payload.type === 'suno:preview') {
        setAudioSource(previewAudio, payload.audio_url);
        setStatus('streaming preview', 'ok');
      } else if (payload.type === 'suno:complete') {
        setAudioSource(finalAudio, payload.audio_url);
        setStatus('slicing loops', 'ok');
      } else if (payload.type === 'suno:loops') {
        renderLoops(payload.loops || []);
        setBusy(false);
        setStatus(`ready: ${(payload.loops || []).length} loops`, 'ok');
      } else if (payload.type === 'suno:error') {
        setBusy(false);
        setStatus(payload.message || 'SunoHub error', 'warn');
      }
    });

    return socketReady;
  }

  async function generate() {
    const description = String(promptInput?.value || '').trim();
    if (!description) {
      setStatus('prompt required', 'warn');
      promptInput?.focus();
      return;
    }

    setBusy(true);
    setStatus('connecting', '');
    renderLoops([]);
    if (previewAudio) {
      previewAudio.removeAttribute('src');
      previewAudio.load();
    }
    if (finalAudio) {
      finalAudio.removeAttribute('src');
      finalAudio.load();
    }

    try {
      const nextSocket = await connect();
      nextSocket.send(JSON.stringify({
        type: 'suno:generate',
        description,
        title: String(titleInput?.value || '').trim(),
      }));
      setStatus('submitted', 'ok');
    } catch (error) {
      setBusy(false);
      setStatus(error instanceof Error ? error.message : 'SunoHub unavailable', 'warn');
    }
  }

  generateBtn?.addEventListener('click', generate);

  return {
    disconnect() {
      socket?.close();
      socket = null;
      socketReady = null;
    },
  };
}
