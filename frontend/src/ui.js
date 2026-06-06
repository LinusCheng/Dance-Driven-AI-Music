const MAX_EVENTS = 70;

function formatCoord(point) {
  return `(${point.x.toFixed(3)}, ${point.y.toFixed(3)}, ${point.z.toFixed(3)})`;
}

function eventTextRotation(direction) {
  if (direction === 'LEFT') {
    return 'Rotating left';
  }
  if (direction === 'RIGHT') {
    return 'Rotating right';
  }
  return null;
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '--';
}

export function createUI(root) {
  const statusText = root.getElementById('statusText');
  const fpsValue = root.getElementById('fpsValue');
  const stageMessage = root.getElementById('stageMessage');
  const retryCameraBtn = root.getElementById('retryCameraBtn');
  const backendStatus = root.getElementById('backendStatus');
  const backendDebugAge = root.getElementById('backendDebugAge');
  const toggleBackendDebug = root.getElementById('toggleBackendDebug');
  const backendFeatureSummary = root.getElementById('backendFeatureSummary');
  const backendMusicSummary = root.getElementById('backendMusicSummary');
  const backendMrt2Summary = root.getElementById('backendMrt2Summary');

  const energyValue = root.getElementById('energyValue');
  const opennessValue = root.getElementById('opennessValue');
  const rotationValue = root.getElementById('rotationValue');

  const leftWristX = root.getElementById('leftWristX');
  const leftWristY = root.getElementById('leftWristY');
  const leftArmHeight = root.getElementById('leftArmHeight');

  const rightWristX = root.getElementById('rightWristX');
  const rightWristY = root.getElementById('rightWristY');
  const rightArmHeight = root.getElementById('rightArmHeight');

  const leftAnkleX = root.getElementById('leftAnkleX');
  const leftAnkleY = root.getElementById('leftAnkleY');
  const leftLegHeight = root.getElementById('leftLegHeight');
  const rightAnkleX = root.getElementById('rightAnkleX');
  const rightAnkleY = root.getElementById('rightAnkleY');
  const rightLegHeight = root.getElementById('rightLegHeight');

  const bodyMap = root.getElementById('bodyMap');
  const bodyHead = bodyMap?.querySelector('[data-part="head"]');
  const bodyTorso = bodyMap?.querySelector('[data-part="torso"]');
  const leftHandEmoji = root.getElementById('leftHandEmoji');
  const rightHandEmoji = root.getElementById('rightHandEmoji');
  const faceMap = root.getElementById('faceMap');
  const faceEmoji = root.getElementById('faceEmoji');
  const eventLog = root.getElementById('eventLog');

  const faceSmileValue = root.getElementById('faceSmileValue');
  const faceMouthOpenValue = root.getElementById('faceMouthOpenValue');
  const faceEyeOpenValue = root.getElementById('faceEyeOpenValue');

  const debugPanel = root.getElementById('debugPanel');
  const toggleDebug = root.getElementById('toggleDebug');
  const dbgNose = root.getElementById('dbgNose');
  const dbgLeftWrist = root.getElementById('dbgLeftWrist');
  const dbgRightWrist = root.getElementById('dbgRightWrist');
  const dbgLeftAnkle = root.getElementById('dbgLeftAnkle');
  const dbgRightAnkle = root.getElementById('dbgRightAnkle');

  let retryHandler = null;
  let backendDebugToggleHandler = null;

  let previous = {
    leftArmHeight: 'LOW',
    rightArmHeight: 'LOW',
    openness: 'CLOSED',
    rotation: 'CENTER',
    energy: 'LOW',
    hasLandmarks: false,
  };

  toggleDebug.addEventListener('click', () => {
    debugPanel.classList.toggle('hidden');
  });

  function pushEvent(text) {
    const item = document.createElement('li');
    item.textContent = `${new Date().toLocaleTimeString()} - ${text}`;
    eventLog.prepend(item);

    while (eventLog.children.length > MAX_EVENTS) {
      eventLog.removeChild(eventLog.lastChild);
    }
  }

  function applyBodyMapVisuals(metricState) {
    const headEnergyRaw = clamp01(metricState.bodyMapVisual?.headEnergy ?? 0);
    const opennessRaw = clamp01(metricState.bodyMapVisual?.openness ?? 0);
    const rotationNorm = Math.max(-1, Math.min(1, (metricState.bodyMapVisual?.torsoRotation ?? 0) / 0.08));

    const headEnergy = clamp01(Math.pow(headEnergyRaw * 1.9, 0.68));
    const openness = clamp01(Math.pow(opennessRaw * 1.75, 0.72));
    const rotationMagnitude = Math.abs(rotationNorm);
    const torsoBias = clamp01(Math.pow(rotationMagnitude, 0.8));
    const rotationSigned = rotationNorm;
    const activeSide = rotationMagnitude < 0.18 ? 'center' : rotationNorm < 0 ? 'left' : 'right';
    const torsoShiftPx = `${(rotationSigned * 7).toFixed(2)}px`;

    if (bodyHead) {
      bodyHead.style.setProperty('--head-energy', headEnergy.toFixed(3));
    }

    if (bodyTorso) {
      bodyTorso.style.setProperty('--body-openness-level', openness.toFixed(3));
      bodyTorso.dataset.torsoSide = activeSide;
      bodyTorso.style.setProperty('--torso-left-intensity', activeSide === 'left' ? torsoBias.toFixed(3) : '0');
      bodyTorso.style.setProperty('--torso-right-intensity', activeSide === 'right' ? torsoBias.toFixed(3) : '0');
      bodyTorso.style.setProperty('--torso-shift', torsoShiftPx);
    }
  }

  function highlightBodyMap(partActivity) {
    bodyMap.querySelectorAll('[data-part]').forEach((element) => {
      const part = element.getAttribute('data-part');
      const intensity = Number(partActivity.limbIntensity?.[part]);
      const isLimb = Number.isFinite(intensity);

      if (isLimb) {
        element.classList.add('limb-spectrum');
        element.style.setProperty('--limb-level', intensity.toFixed(3));
        element.textContent = intensity >= 0.66 ? 'HIGH' : intensity >= 0.33 ? 'MID' : 'LOW';
        element.classList.remove('active');
        return;
      }

      if (part === 'head' || part === 'torso') {
        element.classList.remove('limb-spectrum');
        element.style.removeProperty('--limb-level');
        element.textContent = '';
        element.classList.remove('active');
        return;
      }

      element.classList.remove('limb-spectrum');
      element.style.removeProperty('--limb-level');
      element.textContent = '';
      element.classList.toggle('active', Boolean(partActivity[part]));
    });
  }

  function highlightFaceMap(partActivity) {
    if (!faceMap) {
      return;
    }

    faceMap.querySelectorAll('[data-part]').forEach((element) => {
      const part = element.getAttribute('data-part');
      element.classList.toggle('active', Boolean(partActivity?.[part]));
    });
  }

  function update(metricState) {
    fpsValue.textContent = metricState.fps.toFixed(1);

    const hasLandmarks = Boolean(metricState.landmarks);
    stageMessage.style.opacity = hasLandmarks ? '0' : '1';
    stageMessage.textContent = hasLandmarks
      ? ''
      : 'No pose detected. Stand where your full body is visible.';

    energyValue.textContent = `${metricState.energy.level} (${metricState.energy.value.toFixed(2)})`;
    opennessValue.textContent = metricState.openness.level;
    rotationValue.textContent = metricState.rotation.direction;

    leftWristX.textContent = metricState.leftArm.wristX.toFixed(3);
    leftWristY.textContent = metricState.leftArm.wristY.toFixed(3);
    leftArmHeight.textContent = metricState.leftArm.height;

    rightWristX.textContent = metricState.rightArm.wristX.toFixed(3);
    rightWristY.textContent = metricState.rightArm.wristY.toFixed(3);
    rightArmHeight.textContent = metricState.rightArm.height;

    leftAnkleX.textContent = metricState.leftLeg.x.toFixed(3);
    leftAnkleY.textContent = metricState.leftLeg.y.toFixed(3);
    leftLegHeight.textContent = metricState.leftLeg.height;
    rightAnkleX.textContent = metricState.rightLeg.x.toFixed(3);
    rightAnkleY.textContent = metricState.rightLeg.y.toFixed(3);
    rightLegHeight.textContent = metricState.rightLeg.height;

    highlightBodyMap({ ...metricState.partActivity, limbIntensity: metricState.limbIntensity });
    applyBodyMapVisuals(metricState);
    highlightFaceMap(metricState.face?.partActivity);

    if (faceEmoji) {
      const emoji = metricState.face?.emoji ?? '';
      faceEmoji.textContent = emoji;
      faceEmoji.classList.toggle('active', Boolean(emoji));
    }

    if (leftHandEmoji) {
      const emoji = metricState.hands?.left?.emoji ?? '';
      leftHandEmoji.textContent = emoji;
      leftHandEmoji.classList.toggle('active', Boolean(emoji));
    }

    if (rightHandEmoji) {
      const emoji = metricState.hands?.right?.emoji ?? '';
      rightHandEmoji.textContent = emoji;
      rightHandEmoji.classList.toggle('active', Boolean(emoji));
    }

    faceSmileValue.textContent = metricState.face?.smile?.toFixed(2) ?? '0.00';
    faceMouthOpenValue.textContent = metricState.face?.mouthOpen?.toFixed(2) ?? '0.00';
    faceEyeOpenValue.textContent = metricState.face?.eyeOpen?.toFixed(2) ?? '0.00';

    dbgNose.textContent = formatCoord(metricState.debugPoints.nose);
    dbgLeftWrist.textContent = formatCoord(metricState.debugPoints.leftWrist);
    dbgRightWrist.textContent = formatCoord(metricState.debugPoints.rightWrist);
    dbgLeftAnkle.textContent = formatCoord(metricState.debugPoints.leftAnkle);
    dbgRightAnkle.textContent = formatCoord(metricState.debugPoints.rightAnkle);

    if (metricState.leftArm.height === 'HIGH' && previous.leftArmHeight !== 'HIGH') {
      pushEvent('Left arm raised');
    }

    if (metricState.rightArm.height === 'HIGH' && previous.rightArmHeight !== 'HIGH') {
      pushEvent('Right arm raised');
    }

    if (metricState.openness.level === 'OPEN' && previous.openness !== 'OPEN') {
      pushEvent('Body expanded');
    }

    const rotationEvent = eventTextRotation(metricState.rotation.direction);
    if (rotationEvent && metricState.rotation.direction !== previous.rotation) {
      pushEvent(rotationEvent);
    }

    if (metricState.energy.level === 'HIGH' && previous.energy !== 'HIGH') {
      pushEvent('Fast movement');
    }

    if (metricState.partActivity.leftLeg || metricState.partActivity.rightLeg) {
      if (!previous.hasLandmarks || (metricState.energy.value > 10 && previous.energy === 'LOW')) {
        pushEvent('Leg movement detected');
      }
    }

    previous = {
      leftArmHeight: metricState.leftArm.height,
      rightArmHeight: metricState.rightArm.height,
      openness: metricState.openness.level,
      rotation: metricState.rotation.direction,
      energy: metricState.energy.level,
      hasLandmarks,
    };
  }

  function setStatus(text) {
    statusText.textContent = text;
  }

  function showError(text) {
    statusText.textContent = text;
    stageMessage.style.opacity = '1';
    stageMessage.textContent = text;
    pushEvent(`Error: ${text}`);
  }

  function setBackendStatus(text, connected = false) {
    if (!backendStatus) {
      return;
    }

    backendStatus.textContent = text;
    backendStatus.classList.toggle('connected', connected);
    backendStatus.classList.toggle('disconnected', !connected);
  }

  function updateBackendDebug(debugState) {
    const features = debugState?.features ?? {};
    const music = debugState?.music ?? {};
    const mrt2 = debugState?.mrt2 ?? {};
    const controls = mrt2.controls ?? {};
    const audio = mrt2.audio ?? {};

    if (backendDebugAge) {
      backendDebugAge.textContent = new Date().toLocaleTimeString();
    }

    if (backendFeatureSummary) {
      backendFeatureSummary.textContent =
        `rawEnergy ${formatNumber(features.rawEnergy)} | openness ${formatNumber(features.openness)} | ` +
        `rotation ${formatNumber(features.rotation)} | smile ${formatNumber(features.smile)} | ` +
        `mouth ${formatNumber(features.mouthOpen)} | arms ${features.arms ?? '--'} | gestures ${features.gestures ?? '--'}`;
    }

    if (backendMusicSummary) {
      const sequence = music.gestureSequence?.sequence?.join(' -> ');
      const pair = music.gestureSequence?.gesturePair?.join(' + ');
      const gestureControlText = sequence
        ? ` | sequence ${sequence}`
        : pair
          ? ` | pair ${pair}`
          : '';
      backendMusicSummary.textContent =
        `density ${formatNumber(music.density)} | brightness ${formatNumber(music.brightness)} | ` +
        `tension ${formatNumber(music.tension)} | rhythm ${formatNumber(music.rhythm)} | ` +
        `width ${formatNumber(music.width)} | genre ${music.genre ?? 'adaptive'} | ` +
        `bpm ${music.bpm ?? '--'} | event ${music.event ?? 'none'}${gestureControlText}`;
    }

    if (backendMrt2Summary) {
      const prompt = mrt2.prompt ? `"${mrt2.prompt}"` : 'no prompt yet';
      const buffer = audio.bufferSeconds == null ? '--' : `${formatNumber(audio.bufferSeconds)}s`;
      const underruns = audio.underruns ?? '--';
      const ready = audio.modelReady ? 'ready' : 'warming';
      backendMrt2Summary.textContent =
        `${prompt} | notes ${formatNumber(controls.cfgNotes)} | drums ${formatNumber(controls.cfgDrums)} | ` +
        `temp ${formatNumber(controls.temperature)} | topK ${controls.topK ?? '--'} | ` +
        `buffer ${buffer} | underruns ${underruns} | ${ready}`;
    }
  }

  function setBackendDebugEnabled(enabled) {
    if (toggleBackendDebug) {
      toggleBackendDebug.textContent = enabled ? 'Hide stream' : 'Show stream';
      toggleBackendDebug.setAttribute('aria-pressed', String(enabled));
      toggleBackendDebug.classList.toggle('active', enabled);
    }

    if (!enabled) {
      if (backendDebugAge) {
        backendDebugAge.textContent = 'off';
      }
      if (backendFeatureSummary) {
        backendFeatureSummary.textContent = 'Backend stream is off';
      }
      if (backendMusicSummary) {
        backendMusicSummary.textContent = 'Turn on stream to inspect mapping';
      }
      if (backendMrt2Summary) {
        backendMrt2Summary.textContent = 'Turn on stream to inspect Magenta controls';
      }
    } else if (backendDebugAge) {
      backendDebugAge.textContent = 'waiting';
    }
  }

  function onBackendDebugToggle(handler) {
    if (!toggleBackendDebug) {
      return;
    }

    if (backendDebugToggleHandler) {
      toggleBackendDebug.removeEventListener('click', backendDebugToggleHandler);
    }

    backendDebugToggleHandler = handler;
    toggleBackendDebug.addEventListener('click', backendDebugToggleHandler);
  }

  function onRetry(handler) {
    if (!retryCameraBtn) {
      return;
    }

    if (retryHandler) {
      retryCameraBtn.removeEventListener('click', retryHandler);
    }

    retryHandler = async () => {
      retryCameraBtn.disabled = true;
      try {
        await handler();
      } finally {
        retryCameraBtn.disabled = false;
      }
    };

    retryCameraBtn.addEventListener('click', retryHandler);
  }

  return {
    update,
    setStatus,
    setBackendStatus,
    updateBackendDebug,
    setBackendDebugEnabled,
    onBackendDebugToggle,
    showError,
    onRetry,
  };
}
