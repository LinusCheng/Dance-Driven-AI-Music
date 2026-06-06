import './style.css';
import { createPoseTracker, listCameraDevices } from './tracker.js';
import { createMetricsCalculator } from './metrics.js';
import { createPoseDrawer } from './drawing.js';
import { createUI } from './ui.js';
import { createBackendClient } from './backendSocket.js';
import { createSunoHubClient } from './sunoHubClient.js';

document.querySelector('#app').innerHTML = `
  <div class="app-shell">
    <header class="topbar">
      <div>
        <h1>Dance-Driven Gen Music Prototype</h1>
        <p id="statusText">Initializing camera and pose tracker...</p>
      </div>
      <div class="topbar-actions">
        <div class="camera-control">
          <label class="camera-picker" for="cameraSelect">
            <span>Camera</span>
            <select id="cameraSelect" class="camera-select" disabled>
              <option value="">Default camera</option>
            </select>
          </label>
          <button id="retryCameraBtn" class="retry-btn" type="button">Retry Camera</button>
        </div>
        <div class="fps-chip">FPS <span id="fpsValue">0</span></div>
        <div id="backendStatus" class="backend-status disconnected">RealTimeHub disconnected</div>
      </div>
    </header>

    <main class="main-grid">
      <section class="stage-card">
        <div class="video-wrap">
          <video id="webcam" autoplay playsinline muted></video>
          <canvas id="overlay"></canvas>
          <div id="stageMessage" class="stage-message">Waiting for camera permission...</div>
        </div>
      </section>

      <section class="map-column">
        <section class="panel-section face-map-panel">
          <div class="section-head">
            <h2>Face map</h2>
            <span class="face-map-note">Landmarks + expression cues</span>
          </div>
          <div class="face-map-wrap">
            <div id="faceMap" class="face-map" aria-label="Face map">
              <div data-part="leftBrow" class="face-part face-left-brow"></div>
              <div data-part="rightBrow" class="face-part face-right-brow"></div>
              <div data-part="leftEye" class="face-part face-left-eye"></div>
              <div data-part="rightEye" class="face-part face-right-eye"></div>
              <div data-part="nose" class="face-part face-nose"></div>
              <div data-part="mouth" class="face-part face-mouth"></div>
              <div data-part="jaw" class="face-jaw-segment"></div>
            </div>
            <div id="faceEmoji" class="face-emoji" aria-label="Face expression emoji"></div>
          </div>

          <div class="face-expression-grid" aria-label="Facial expression cues">
            <div class="face-expression-card">
              <span>Smile</span>
              <strong id="faceSmileValue">0.00</strong>
            </div>
            <div class="face-expression-card">
              <span>Mouth open</span>
              <strong id="faceMouthOpenValue">0.00</strong>
            </div>
            <div class="face-expression-card">
              <span>Eye open</span>
              <strong id="faceEyeOpenValue">0.00</strong>
            </div>
          </div>
        </section>

        <section class="panel-section body-map-panel">
          <h2>Body map</h2>
          <div id="bodyMap" class="body-map human-map" aria-label="Body map">
            <div data-part="head" class="body-part body-head" aria-label="Head"></div>
            <div data-part="leftArm" class="body-part body-left-arm" aria-label="Left arm"></div>
            <div data-part="rightArm" class="body-part body-right-arm" aria-label="Right arm"></div>
            <div id="leftHandEmoji" class="hand-emoji hand-emoji-left" aria-label="Left hand gesture"></div>
            <div id="rightHandEmoji" class="hand-emoji hand-emoji-right" aria-label="Right hand gesture"></div>
            <div data-part="torso" class="body-part body-torso"></div>
            <div data-part="leftLeg" class="body-part body-left-leg" aria-label="Left leg"></div>
            <div data-part="rightLeg" class="body-part body-right-leg" aria-label="Right leg"></div>
          </div>
        </section>
      </section>

      <section class="data-column">
        <section class="panel-section nested-panel">
          <h2>Body</h2>
          <div class="body-metrics">
            <div class="metric-row metric-row-compact"><span>Movement energy</span><strong id="energyValue">LOW (0.00)</strong></div>
            <div class="metric-row metric-row-compact"><span>Body openness</span><strong id="opennessValue">MID</strong></div>
            <div class="metric-row metric-row-compact"><span>Torso rotation</span><strong id="rotationValue">CENTER</strong></div>
          </div>
        </section>

        <section class="panel-section nested-panel">
          <h2>Limbs</h2>
          <div class="limb-grid">
            <section class="mini-limb-card">
              <h3>Left arm</h3>
              <div class="metric-row metric-row-inline"><span>Wrist</span><strong class="coord-pair"><span><em>x</em><span id="leftWristX">0.000</span></span><span><em>y</em><span id="leftWristY">0.000</span></span></strong></div>
              <div class="metric-row"><span>Arm height</span><strong id="leftArmHeight">LOW</strong></div>
            </section>

            <section class="mini-limb-card">
              <h3>Right arm</h3>
              <div class="metric-row metric-row-inline"><span>Wrist</span><strong class="coord-pair"><span><em>x</em><span id="rightWristX">0.000</span></span><span><em>y</em><span id="rightWristY">0.000</span></span></strong></div>
              <div class="metric-row"><span>Arm height</span><strong id="rightArmHeight">LOW</strong></div>
            </section>

            <section class="mini-limb-card">
              <h3>Left leg</h3>
              <div class="metric-row metric-row-inline"><span>Ankle</span><strong class="coord-pair"><span><em>x</em><span id="leftAnkleX">0.000</span></span><span><em>y</em><span id="leftAnkleY">0.000</span></span></strong></div>
              <div class="metric-row"><span>Height</span><strong id="leftLegHeight">LOW</strong></div>
            </section>

            <section class="mini-limb-card">
              <h3>Right leg</h3>
              <div class="metric-row metric-row-inline"><span>Ankle</span><strong class="coord-pair"><span><em>x</em><span id="rightAnkleX">0.000</span></span><span><em>y</em><span id="rightAnkleY">0.000</span></span></strong></div>
              <div class="metric-row"><span>Height</span><strong id="rightLegHeight">LOW</strong></div>
            </section>
          </div>
        </section>
      </section>

      <section class="manual-prompt-panel">
        <div class="section-head">
          <h2>Prompt</h2>
          <span id="manualPromptStatus" class="backend-debug-age">movement prompt</span>
        </div>
        <textarea id="manualPromptInput" class="manual-prompt-input" rows="4" maxlength="280" placeholder="acid house with bright stabs and punchy drums"></textarea>
        <div class="manual-prompt-actions">
          <button id="sendManualPrompt" class="backend-debug-toggle" type="button">Send prompt</button>
          <button id="clearManualPrompt" class="backend-debug-toggle" type="button">Clear</button>
        </div>
      </section>
    </main>

    <section class="bottom-grid">
      <section class="backend-debug-panel">
        <div class="section-head">
          <h2>RealTimeHub stream</h2>
          <div class="backend-debug-actions">
            <span id="backendDebugAge" class="backend-debug-age">off</span>
            <button id="toggleBackendDebug" class="backend-debug-toggle" type="button" aria-pressed="false">Show stream</button>
          </div>
        </div>

        <div class="backend-debug-grid">
          <section class="backend-debug-block">
            <h3>Features</h3>
            <div id="backendFeatureSummary" class="backend-debug-line">No backend data yet</div>
          </section>

          <section class="backend-debug-block">
            <h3>Music</h3>
            <div id="backendMusicSummary" class="backend-debug-line">No mapping yet</div>
          </section>

          <section class="backend-debug-block backend-debug-wide">
            <h3>Magenta</h3>
            <div id="backendMrt2Summary" class="backend-debug-line">Waiting for MRT2 status</div>
          </section>
        </div>
      </section>

      <section class="suno-panel">
        <div class="section-head">
          <h2>Suno loops</h2>
          <span id="sunoStatus" class="backend-debug-age">offline</span>
        </div>
        <input id="sunoTitleInput" class="suno-input" maxlength="80" placeholder="Optional title" />
        <textarea id="sunoPromptInput" class="suno-input suno-textarea" rows="3" maxlength="500" placeholder="late-night disco house, tight bass, bright hooks"></textarea>
        <div class="suno-actions">
          <button id="sunoGenerateBtn" class="backend-debug-toggle" type="button">Generate</button>
        </div>
        <div class="suno-audio-grid">
          <label>
            <span>Preview</span>
            <audio id="sunoPreviewAudio" controls></audio>
          </label>
          <label>
            <span>Final</span>
            <audio id="sunoFinalAudio" controls></audio>
          </label>
        </div>
        <div id="sunoLoopGrid" class="suno-loop-grid" aria-label="Generated Suno loops"></div>
      </section>

      <section class="event-panel">
        <h2>Event log</h2>
        <ul id="eventLog"></ul>
      </section>

      <section class="panel-section debug-panel">
        <div class="section-head">
          <h2>Debug landmarks</h2>
          <button id="toggleDebug" type="button">Toggle debug</button>
        </div>
        <section id="debugPanel" class="panel-section hidden">
          <div class="debug-grid">
            <div>Nose <span id="dbgNose">(0, 0)</span></div>
            <div>Left wrist <span id="dbgLeftWrist">(0, 0)</span></div>
            <div>Right wrist <span id="dbgRightWrist">(0, 0)</span></div>
            <div>Left ankle <span id="dbgLeftAnkle">(0, 0)</span></div>
            <div>Right ankle <span id="dbgRightAnkle">(0, 0)</span></div>
          </div>
        </section>
      </section>
    </section>
  </div>
`;

const videoElement = document.getElementById('webcam');
const canvasElement = document.getElementById('overlay');

const ui = createUI(document);
const backendClient = createBackendClient(ui);
const sunoHubClient = createSunoHubClient(document);
ui.onBackendDebugToggle(() => {
  backendClient.toggleBackendDebug();
});
ui.onManualPromptSubmit((prompt) => {
  backendClient.setManualPrompt(prompt);
});
ui.onManualPromptClear(() => {
  backendClient.setManualPrompt('');
});
const metricsCalculator = createMetricsCalculator();
const poseDrawer = createPoseDrawer(canvasElement);
const cameraSelect = document.getElementById('cameraSelect');

let tracker;
let currentCameraDeviceId = '';
let cameraOptions = [];

function renderCameraOptions(devices) {
  if (!cameraSelect) {
    return;
  }

  const previousValue = cameraSelect.value || currentCameraDeviceId;
  cameraSelect.innerHTML = '<option value="">Default camera</option>';

  devices.forEach((device, index) => {
    const option = document.createElement('option');
    option.value = device.deviceId;
    option.textContent = device.label || `Camera ${index + 1}`;
    cameraSelect.appendChild(option);
  });

  const availableIds = new Set(devices.map((device) => device.deviceId));
  const nextValue = availableIds.has(previousValue) ? previousValue : '';
  cameraSelect.value = nextValue;
  currentCameraDeviceId = nextValue;
  cameraSelect.disabled = devices.length === 0;
}

async function refreshCameraList() {
  try {
    const devices = await listCameraDevices();
    cameraOptions = devices;
    renderCameraOptions(cameraOptions);
  } catch (error) {
    ui.showError(error instanceof Error ? error.message : 'Unable to read available cameras.');
  }
}

async function startTracker(deviceId = currentCameraDeviceId) {
  currentCameraDeviceId = deviceId || '';

  if (tracker) {
    tracker.stop();
  }

  tracker = await createPoseTracker({
    videoElement,
    onFrame: ({
      landmarks,
      faceLandmarks,
      faceBlendshapes,
      handLandmarks,
      handHandednesses,
      fps,
      timestampMs,
      width,
      height,
    }) => {
      const metrics = metricsCalculator({
        landmarks,
        faceLandmarks,
        faceBlendshapes,
        handLandmarks,
        handHandednesses,
        fps,
        timestampMs,
      });
      poseDrawer.draw(landmarks, width, height);

      const movementData = {
        fps,
        energy: metrics.energy.value,
        openness: metrics.openness.value,
        rotation: metrics.rotation.value,
        smile: metrics.face.smile,
        mouthOpen: metrics.face.mouthOpen,
        leftArmHeight: metrics.leftArm.height,
        rightArmHeight: metrics.rightArm.height,
        gestureLeft: metrics.hands.left.gesture,
        gestureRight: metrics.hands.right.gesture,
        timestamp: timestampMs,
      };

      window.movementData = movementData;
      backendClient.updateMovementData(movementData);
      ui.update(metrics);
    },
    onStatus: (text) => ui.setStatus(text),
    onError: (errorText) => {
      ui.showError(errorText);
    },
  });

  tracker.setCameraDevice(deviceId);
  await tracker.start();

  await refreshCameraList();

  ui.onRetry(async () => {
    if (!tracker) {
      return;
    }

    ui.setStatus('Retrying camera and tracker...');
    await startTracker(currentCameraDeviceId);
  });
}

async function boot() {
  try {
    if (cameraSelect) {
      cameraSelect.addEventListener('change', async (event) => {
        currentCameraDeviceId = event.target.value;
        ui.setStatus('Switching camera...');
        try {
          await startTracker(currentCameraDeviceId);
        } catch (error) {
          ui.showError(error instanceof Error ? error.message : 'Unable to switch camera.');
        }
      });
    }

    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', async () => {
        await refreshCameraList();
      });
    }

    await startTracker(currentCameraDeviceId);
  } catch (error) {
    ui.showError(error instanceof Error ? error.message : 'Unable to initialize app.');
  }
}

boot();

window.addEventListener('beforeunload', () => {
  if (tracker) {
    tracker.stop();
  }
  sunoHubClient.disconnect();
});
