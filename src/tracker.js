import { FaceLandmarker, FilesetResolver, HandLandmarker, PoseLandmarker } from '@mediapipe/tasks-vision';

const WASM_ROOT = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm';
const MODEL_ASSET_PATH =
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task';
const FACE_MODEL_ASSET_PATH =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task';
const HAND_MODEL_ASSET_PATH =
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';

export async function listCameraDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    return [];
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((device) => device.kind === 'videoinput');
}

async function setupCamera(videoElement, deviceId) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('Webcam is not supported in this browser.');
  }

  let stream;
  try {
    const videoConstraints = deviceId
      ? {
          deviceId: { exact: deviceId },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        }
      : {
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 },
        };

    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: videoConstraints,
    });
  } catch (primaryError) {
    try {
      // Safari and some camera/device combinations can reject strict constraints.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: true,
      });
    } catch (secondaryError) {
      const error = secondaryError || primaryError;
      const name = error && typeof error === 'object' && 'name' in error ? error.name : 'UnknownError';

      if (name === 'NotAllowedError') {
        const secureHint =
          window.isSecureContext
            ? ''
            : ' Open this app from a secure origin (https or localhost).';
        throw new Error(
          'Camera permission blocked. In Safari, open Settings for This Website and set Camera to Allow, then reload the page.' +
            secureHint
        );
      }

      if (name === 'NotFoundError') {
        throw new Error('No camera device was found. Connect a webcam and retry.');
      }

      if (name === 'NotReadableError') {
        throw new Error('Camera is busy in another app. Close other camera apps and retry.');
      }

      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Unable to access webcam: ${message}`);
    }
  }

  videoElement.srcObject = stream;
  await videoElement.play();

  if (!videoElement.videoWidth || !videoElement.videoHeight) {
    await new Promise((resolve) => {
      let settled = false;

      const finish = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };

      if (videoElement.videoWidth && videoElement.videoHeight) {
        finish();
        return;
      }

      const timeoutId = window.setTimeout(finish, 1500);
      const onReady = () => {
        window.clearTimeout(timeoutId);
        finish();
      };

      videoElement.addEventListener('loadedmetadata', onReady, { once: true });
      videoElement.addEventListener('loadeddata', onReady, { once: true });
    });
  }

  return stream;
}

async function createTaskWithFallback({ onStatus, label, createWithDelegate }) {
  try {
    return await createWithDelegate('GPU');
  } catch (gpuError) {
    onStatus(`GPU ${label} backend unavailable, retrying with CPU...`);
    try {
      return await createWithDelegate('CPU');
    } catch (cpuError) {
      const gpuMessage = gpuError instanceof Error ? gpuError.message : String(gpuError);
      const cpuMessage = cpuError instanceof Error ? cpuError.message : String(cpuError);
      throw new Error(`${label} failed to initialize (GPU: ${gpuMessage}; CPU: ${cpuMessage})`);
    }
  }
}

async function createPoseLandmarker(vision, onStatus) {
  const createWithDelegate = (delegate) =>
    PoseLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: MODEL_ASSET_PATH,
        delegate,
      },
      runningMode: 'VIDEO',
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });

  return createTaskWithFallback({
    onStatus,
    label: 'pose',
    createWithDelegate,
  });
}

async function createFaceLandmarker(vision, onStatus) {
  const createWithDelegate = (delegate) =>
    FaceLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: FACE_MODEL_ASSET_PATH,
        delegate,
      },
      runningMode: 'VIDEO',
      numFaces: 1,
      minFaceDetectionConfidence: 0.5,
      minFacePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
      outputFaceBlendshapes: true,
    });

  return createTaskWithFallback({
    onStatus,
    label: 'face',
    createWithDelegate,
  });
}

async function createHandLandmarker(vision, onStatus) {
  const createWithDelegate = (delegate) =>
    HandLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath: HAND_MODEL_ASSET_PATH,
        delegate,
      },
      runningMode: 'VIDEO',
      numHands: 2,
      minHandDetectionConfidence: 0.5,
      minHandPresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });

  return createTaskWithFallback({
    onStatus,
    label: 'hand',
    createWithDelegate,
  });
}

export async function createPoseTracker({ videoElement, onFrame, onStatus, onError }) {
  let poseLandmarker = null;
  let faceLandmarker = null;
  let handLandmarker = null;
  let stream = null;
  let rafId = null;
  let running = false;
  let cameraDeviceId = null;
  let previousTimestamp = 0;
  let smoothedFps = 0;

  const cleanupResources = () => {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }

    if (poseLandmarker) {
      poseLandmarker.close();
      poseLandmarker = null;
    }

    if (faceLandmarker) {
      faceLandmarker.close();
      faceLandmarker = null;
    }

    if (handLandmarker) {
      handLandmarker.close();
      handLandmarker = null;
    }

    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }

    previousTimestamp = 0;
    smoothedFps = 0;
  };

  const getVideoDimensions = () => {
    const trackSettings = stream?.getVideoTracks?.()[0]?.getSettings?.() ?? {};

    return {
      width: videoElement.videoWidth || trackSettings.width || 1280,
      height: videoElement.videoHeight || trackSettings.height || 720,
    };
  };

  const tick = (timestampMs) => {
    if (!running) {
      return;
    }

    if (previousTimestamp > 0) {
      const instantFps = 1000 / Math.max(1, timestampMs - previousTimestamp);
      smoothedFps = smoothedFps === 0 ? instantFps : smoothedFps * 0.8 + instantFps * 0.2;
    }
    previousTimestamp = timestampMs;

    try {
      if (
        videoElement.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
        poseLandmarker &&
        faceLandmarker &&
        handLandmarker
      ) {
        const poseResult = poseLandmarker.detectForVideo(videoElement, timestampMs);
        const faceResult = faceLandmarker.detectForVideo(videoElement, timestampMs);
        const handResult = handLandmarker.detectForVideo(videoElement, timestampMs);
        const landmarks = poseResult.landmarks?.[0] ?? null;
        const faceLandmarks = faceResult.faceLandmarks?.[0] ?? null;
        const faceBlendshapes = faceResult.faceBlendshapes ?? [];
        const handLandmarks = handResult.landmarks ?? [];
        const handHandednesses = handResult.handednesses ?? [];
        const { width, height } = getVideoDimensions();

        onFrame({
          landmarks,
          faceLandmarks,
          faceBlendshapes,
          handLandmarks,
          handHandednesses,
          fps: Number((smoothedFps || 0).toFixed(1)),
          timestampMs,
          width,
          height,
        });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Pose tracking failed.';
      onError(message);
    }

    rafId = requestAnimationFrame(tick);
  };

  return {
    async start() {
      if (running) {
        return;
      }

      try {
        onStatus('Requesting webcam permission...');
        stream = await setupCamera(videoElement, cameraDeviceId);
        const vision = await FilesetResolver.forVisionTasks(WASM_ROOT);

        onStatus('Loading Pose Landmarker model...');
        poseLandmarker = await createPoseLandmarker(vision, onStatus);

        onStatus('Loading Face Landmarker model...');
        faceLandmarker = await createFaceLandmarker(vision, onStatus);

        onStatus('Loading Hand Landmarker model...');
        handLandmarker = await createHandLandmarker(vision, onStatus);

        running = true;
        onStatus('Tracking live pose, face, and hands.');
        rafId = requestAnimationFrame(tick);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        cleanupResources();
        onError(`Tracker startup failed: ${message}`);
        running = false;
      }
    },

    stop() {
      running = false;

      cleanupResources();

      onStatus('Tracking stopped.');
    },

    setCameraDevice(deviceId) {
      cameraDeviceId = deviceId || null;
    },
  };
}
