const IDX = {
  nose: 0,
  leftShoulder: 11,
  rightShoulder: 12,
  leftWrist: 15,
  rightWrist: 16,
  leftHip: 23,
  rightHip: 24,
  leftAnkle: 27,
  rightAnkle: 28,
};

const HAND_IDX = {
  wrist: 0,
  thumbMcp: 2,
  thumbTip: 4,
  indexMcp: 5,
  indexPip: 6,
  indexTip: 8,
  middleMcp: 9,
  middlePip: 10,
  middleTip: 12,
  ringMcp: 13,
  ringPip: 14,
  ringTip: 16,
  pinkyMcp: 17,
  pinkyPip: 18,
  pinkyTip: 20,
};

const HAND_GESTURE_EMOJI = {
  openPalm: '✋',
  fist: '✊',
  pinch: '🤏',
  point: '☝️',
  peace: '✌️',
  openCloseTransition: '🔄',
};

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function smoothValue(previous, next, alpha) {
  if (Number.isNaN(previous)) {
    return next;
  }
  return previous * (1 - alpha) + next * alpha;
}

function distance2D(a, b) {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

function handednessLabel(handednessEntry) {
  const label = handednessEntry?.[0]?.categoryName || handednessEntry?.[0]?.displayName || '';
  const normalized = label.toLowerCase();

  if (normalized.includes('left')) {
    return 'left';
  }
  if (normalized.includes('right')) {
    return 'right';
  }
  return null;
}

function fingerExtended(landmarks, mcpIdx, pipIdx, tipIdx) {
  const mcp = landmarks?.[mcpIdx];
  const pip = landmarks?.[pipIdx];
  const tip = landmarks?.[tipIdx];

  if (!mcp || !pip || !tip) {
    return false;
  }

  return tip.y < pip.y && pip.y < mcp.y;
}

function handGestureFromLandmarks(landmarks, previousOpenness = NaN) {
  if (!Array.isArray(landmarks) || landmarks.length < 21) {
    return { key: null, openness: NaN };
  }

  const palmSize = Math.max(
    1e-5,
    distance2D(landmarks[HAND_IDX.wrist], landmarks[HAND_IDX.middleMcp])
  );

  const indexExtended = fingerExtended(landmarks, HAND_IDX.indexMcp, HAND_IDX.indexPip, HAND_IDX.indexTip);
  const middleExtended = fingerExtended(landmarks, HAND_IDX.middleMcp, HAND_IDX.middlePip, HAND_IDX.middleTip);
  const ringExtended = fingerExtended(landmarks, HAND_IDX.ringMcp, HAND_IDX.ringPip, HAND_IDX.ringTip);
  const pinkyExtended = fingerExtended(landmarks, HAND_IDX.pinkyMcp, HAND_IDX.pinkyPip, HAND_IDX.pinkyTip);

  const thumbTip = landmarks[HAND_IDX.thumbTip];
  const thumbMcp = landmarks[HAND_IDX.thumbMcp];
  const indexTip = landmarks[HAND_IDX.indexTip];
  const thumbIndexDistNorm = distance2D(thumbTip, indexTip) / palmSize;
  const thumbExtended = distance2D(thumbTip, thumbMcp) / palmSize > 0.55;

  const opennessScore =
    (distance2D(landmarks[HAND_IDX.indexTip], landmarks[HAND_IDX.indexMcp]) +
      distance2D(landmarks[HAND_IDX.middleTip], landmarks[HAND_IDX.middleMcp]) +
      distance2D(landmarks[HAND_IDX.ringTip], landmarks[HAND_IDX.ringMcp]) +
      distance2D(landmarks[HAND_IDX.pinkyTip], landmarks[HAND_IDX.pinkyMcp])) /
    (4 * palmSize);

  const fourFingersExtended = indexExtended && middleExtended && ringExtended && pinkyExtended;
  const palmClearlyOpen = fourFingersExtended && opennessScore > 0.94;

  let key = null;

  if (thumbIndexDistNorm < 0.24 && !palmClearlyOpen) {
    key = 'pinch';
  } else if (indexExtended && middleExtended && !ringExtended && !pinkyExtended) {
    key = 'peace';
  } else if (indexExtended && !middleExtended && !ringExtended && !pinkyExtended) {
    key = 'point';
  } else if (palmClearlyOpen || (fourFingersExtended && thumbExtended)) {
    key = 'openPalm';
  } else if (!indexExtended && !middleExtended && !ringExtended && !pinkyExtended && opennessScore < 0.72) {
    key = 'fist';
  }

  const hasPrev = Number.isFinite(previousOpenness);
  const transitionDetected =
    hasPrev &&
    Math.abs(opennessScore - previousOpenness) > 0.36 &&
    ((opennessScore > 1.22 && previousOpenness < 0.84) ||
      (opennessScore < 0.84 && previousOpenness > 1.22));

  if (transitionDetected) {
    key = 'openCloseTransition';
  }

  return { key, openness: opennessScore };
}

function landmarkOrFallback(landmarks, index, fallback = { x: 0, y: 0, z: 0, visibility: 0 }) {
  return landmarks?.[index] ?? fallback;
}

function blendshapeScore(blendshapes, name) {
  const categories = blendshapes?.[0]?.categories ?? [];
  const category = categories.find(
    (entry) => entry.categoryName === name || entry.displayName === name
  );

  return category?.score ?? 0;
}

function classifyBand(value, lowThreshold, highThreshold, labels) {
  if (value >= highThreshold) {
    return labels.high;
  }
  if (value >= lowThreshold) {
    return labels.mid;
  }
  return labels.low;
}

function classifyFaceEmoji({ smile, mouthOpen, eyeOpenLeft, eyeOpenRight, browRaise, mouthDelta }) {
  const eyeOpenAvg = (eyeOpenLeft + eyeOpenRight) * 0.5;
  const eyeDiff = Math.abs(eyeOpenLeft - eyeOpenRight);
  const winkDetected = eyeDiff > 0.45 && Math.max(eyeOpenLeft, eyeOpenRight) > 0.6 && Math.min(eyeOpenLeft, eyeOpenRight) < 0.35;

  if (winkDetected) {
    return '😉';
  }

  if (mouthOpen > 0.72 && browRaise > 0.55) {
    return '😲';
  }

  if (mouthOpen > 0.55 && eyeOpenAvg > 0.62 && browRaise > 0.35) {
    return '😮';
  }

  if (smile > 0.62 && mouthOpen > 0.34) {
    return '😆';
  }

  if (smile > 0.6) {
    return '😄';
  }

  if (smile < 0.28 && eyeOpenAvg < 0.36) {
    return '😔';
  }

  if (eyeOpenAvg < 0.36) {
    return '😪';
  }

  if (smile < 0.3 && browRaise > 0.22 && mouthOpen < 0.22) {
    return '🤔';
  }

  if (mouthOpen > 0.3 && mouthDelta > 0.085 && smile < 0.58) {
    return '🎤';
  }

  if (smile < 0.25 && mouthOpen < 0.2 && eyeOpenAvg > 0.42 && eyeOpenAvg < 0.76) {
    return '😐';
  }

  return '😐';
}

export function createMetricsCalculator() {
  let previousLandmarks = null;
  let smoothedEnergy = 0;
  let smoothedOpeness = 0.2;
  let smoothedRotation = 0;
  let smoothedLeftArmScore = 0;
  let smoothedRightArmScore = 0;
  let smoothedLeftLegScore = 0;
  let smoothedRightLegScore = 0;
  let smoothedHeadEnergy = 0;
  let smoothedLeftArmIntensity = 0;
  let smoothedRightArmIntensity = 0;
  let smoothedLeftLegIntensity = 0;
  let smoothedRightLegIntensity = 0;
  let smoothedLeftLegMovement = 0;
  let smoothedRightLegMovement = 0;
  let smoothedFaceSmile = 0;
  let smoothedFaceMouthOpen = 0;
  let smoothedFaceEyeOpenLeft = 0;
  let smoothedFaceEyeOpenRight = 0;
  let smoothedFaceBrowRaise = 0;
  let previousSmoothedFaceMouthOpen = NaN;
  let previousHandOpenness = {
    left: NaN,
    right: NaN,
  };

  return ({ landmarks, faceLandmarks, faceBlendshapes, handLandmarks = [], handHandednesses = [], fps }) => {
    const faceDetected = Boolean(faceLandmarks?.length);
    const smileRaw = Math.max(
      blendshapeScore(faceBlendshapes, 'mouthSmileLeft'),
      blendshapeScore(faceBlendshapes, 'mouthSmileRight')
    );
    const mouthOpenRaw = blendshapeScore(faceBlendshapes, 'jawOpen');
    const eyeOpenLeftRaw = 1 - blendshapeScore(faceBlendshapes, 'eyeBlinkLeft');
    const eyeOpenRightRaw = 1 - blendshapeScore(faceBlendshapes, 'eyeBlinkRight');
    const browRaiseRaw = Math.max(
      blendshapeScore(faceBlendshapes, 'browInnerUp'),
      blendshapeScore(faceBlendshapes, 'browOuterUpLeft'),
      blendshapeScore(faceBlendshapes, 'browOuterUpRight')
    );

    smoothedFaceSmile = smoothValue(smoothedFaceSmile, smileRaw, 0.3);
    smoothedFaceMouthOpen = smoothValue(smoothedFaceMouthOpen, mouthOpenRaw, 0.3);
    smoothedFaceEyeOpenLeft = smoothValue(smoothedFaceEyeOpenLeft, eyeOpenLeftRaw, 0.3);
    smoothedFaceEyeOpenRight = smoothValue(smoothedFaceEyeOpenRight, eyeOpenRightRaw, 0.3);
    smoothedFaceBrowRaise = smoothValue(smoothedFaceBrowRaise, browRaiseRaw, 0.3);

    const mouthDelta = Number.isFinite(previousSmoothedFaceMouthOpen)
      ? Math.abs(smoothedFaceMouthOpen - previousSmoothedFaceMouthOpen)
      : 0;
    previousSmoothedFaceMouthOpen = smoothedFaceMouthOpen;

    const faceEmoji = faceDetected
      ? classifyFaceEmoji({
          smile: smoothedFaceSmile,
          mouthOpen: smoothedFaceMouthOpen,
          eyeOpenLeft: smoothedFaceEyeOpenLeft,
          eyeOpenRight: smoothedFaceEyeOpenRight,
          browRaise: smoothedFaceBrowRaise,
          mouthDelta,
        })
      : '';

    const facePartActivity = {
      leftBrow: faceDetected && smoothedFaceBrowRaise > 0.12,
      rightBrow: faceDetected && smoothedFaceBrowRaise > 0.12,
      leftEye: faceDetected && smoothedFaceEyeOpenLeft > 0.42,
      rightEye: faceDetected && smoothedFaceEyeOpenRight > 0.42,
      nose: faceDetected,
      mouth: faceDetected && (smoothedFaceMouthOpen > 0.08 || smoothedFaceSmile > 0.1),
      jaw: faceDetected && smoothedFaceMouthOpen > 0.05,
    };

    if (!landmarks) {
      previousHandOpenness.left = NaN;
      previousHandOpenness.right = NaN;
      smoothedEnergy = smoothValue(smoothedEnergy, 0, 0.18);
      smoothedHeadEnergy = smoothValue(smoothedHeadEnergy, 0, 0.22);
      smoothedOpeness = smoothValue(smoothedOpeness, 0, 0.2);
      smoothedRotation = smoothValue(smoothedRotation, 0, 0.2);
      smoothedLeftArmIntensity = smoothValue(smoothedLeftArmIntensity, 0, 0.25);
      smoothedRightArmIntensity = smoothValue(smoothedRightArmIntensity, 0, 0.25);
      smoothedLeftLegIntensity = smoothValue(smoothedLeftLegIntensity, 0, 0.25);
      smoothedRightLegIntensity = smoothValue(smoothedRightLegIntensity, 0, 0.25);
      smoothedLeftLegScore = smoothValue(smoothedLeftLegScore, 0, 0.25);
      smoothedRightLegScore = smoothValue(smoothedRightLegScore, 0, 0.25);
      smoothedLeftLegMovement = smoothValue(smoothedLeftLegMovement, 0, 0.2);
      smoothedRightLegMovement = smoothValue(smoothedRightLegMovement, 0, 0.2);

      return {
        fps,
        energy: {
          level: 'LOW',
          value: Number(smoothedEnergy.toFixed(2)),
        },
        openness: {
          level: 'CLOSED',
          value: Number(smoothedOpeness.toFixed(3)),
        },
        rotation: {
          direction: 'CENTER',
          value: Number(smoothedRotation.toFixed(3)),
        },
        leftArm: { wristX: 0, wristY: 0, height: 'LOW' },
        rightArm: { wristX: 0, wristY: 0, height: 'LOW' },
        leftLeg: { x: 0, y: 0, height: 'LOW', movement: Number(smoothedLeftLegMovement.toFixed(3)) },
        rightLeg: { x: 0, y: 0, height: 'LOW', movement: Number(smoothedRightLegMovement.toFixed(3)) },
        partActivity: {
          head: false,
          leftArm: false,
          rightArm: false,
          torso: false,
          leftLeg: false,
          rightLeg: false,
        },
        limbIntensity: {
          leftArm: Number(smoothedLeftArmIntensity.toFixed(3)),
          rightArm: Number(smoothedRightArmIntensity.toFixed(3)),
          leftLeg: Number(smoothedLeftLegIntensity.toFixed(3)),
          rightLeg: Number(smoothedRightLegIntensity.toFixed(3)),
        },
        bodyMapVisual: {
          headEnergy: Number(smoothedHeadEnergy.toFixed(3)),
          openness: Number(clamp01(smoothedOpeness).toFixed(3)),
          torsoRotation: Number(smoothedRotation.toFixed(3)),
        },
        face: {
          detected: faceDetected,
          smile: Number(smoothedFaceSmile.toFixed(2)),
          mouthOpen: Number(smoothedFaceMouthOpen.toFixed(2)),
          eyeOpen: Number(((smoothedFaceEyeOpenLeft + smoothedFaceEyeOpenRight) * 0.5).toFixed(2)),
          browRaise: Number(smoothedFaceBrowRaise.toFixed(2)),
          emoji: faceEmoji,
          partActivity: facePartActivity,
        },
        hands: {
          left: { detected: false, gesture: null, emoji: '' },
          right: { detected: false, gesture: null, emoji: '' },
        },
        debugPoints: {
          nose: { x: 0, y: 0, z: 0 },
          leftWrist: { x: 0, y: 0, z: 0 },
          rightWrist: { x: 0, y: 0, z: 0 },
          leftAnkle: { x: 0, y: 0, z: 0 },
          rightAnkle: { x: 0, y: 0, z: 0 },
        },
        landmarks: null,
      };
    }

    const leftShoulder = landmarkOrFallback(landmarks, IDX.leftShoulder);
    const rightShoulder = landmarkOrFallback(landmarks, IDX.rightShoulder);
    const leftWrist = landmarkOrFallback(landmarks, IDX.leftWrist);
    const rightWrist = landmarkOrFallback(landmarks, IDX.rightWrist);
    const leftHip = landmarkOrFallback(landmarks, IDX.leftHip);
    const rightHip = landmarkOrFallback(landmarks, IDX.rightHip);
    const leftAnkle = landmarkOrFallback(landmarks, IDX.leftAnkle);
    const rightAnkle = landmarkOrFallback(landmarks, IDX.rightAnkle);
    const nose = landmarkOrFallback(landmarks, IDX.nose);

    const shoulderDistance = distance2D(leftShoulder, rightShoulder);
    const wristDistance = distance2D(leftWrist, rightWrist);
    const opennessRaw = clamp01(shoulderDistance * 0.7 + wristDistance * 0.8);
    smoothedOpeness = smoothValue(smoothedOpeness, opennessRaw, 0.25);
    const opennessLevel = classifyBand(smoothedOpeness, 0.28, 0.44, {
      low: 'CLOSED',
      mid: 'MID',
      high: 'OPEN',
    });

    const leftArmScore = leftShoulder.y - leftWrist.y;
    const rightArmScore = rightShoulder.y - rightWrist.y;
    smoothedLeftArmScore = smoothValue(smoothedLeftArmScore, leftArmScore, 0.35);
    smoothedRightArmScore = smoothValue(smoothedRightArmScore, rightArmScore, 0.35);

    const leftArmHeight = classifyBand(smoothedLeftArmScore, 0.045, 0.16, {
      low: 'LOW',
      mid: 'MID',
      high: 'HIGH',
    });
    const rightArmHeight = classifyBand(smoothedRightArmScore, 0.045, 0.16, {
      low: 'LOW',
      mid: 'MID',
      high: 'HIGH',
    });

    const rawRotation = rightShoulder.z - leftShoulder.z;
    smoothedRotation = smoothValue(smoothedRotation, rawRotation, 0.25);
    let rotationDirection = 'CENTER';
    if (smoothedRotation > 0.045) {
      rotationDirection = 'LEFT';
    } else if (smoothedRotation < -0.045) {
      rotationDirection = 'RIGHT';
    }

    let movementRaw = 0;
    let headMovement = 0;
    let leftArmMovement = 0;
    let rightArmMovement = 0;
    let torsoMovement = 0;
    let leftLegMovement = 0;
    let rightLegMovement = 0;

    if (previousLandmarks) {
      for (let i = 0; i < landmarks.length; i += 1) {
        const current = landmarks[i];
        const previous = previousLandmarks[i];
        movementRaw += distance2D(current, previous);
      }
      movementRaw /= landmarks.length;

      headMovement = distance2D(nose, previousLandmarks[IDX.nose]);
      leftArmMovement = distance2D(leftWrist, previousLandmarks[IDX.leftWrist]);
      rightArmMovement = distance2D(rightWrist, previousLandmarks[IDX.rightWrist]);

      const prevLeftHip = previousLandmarks[IDX.leftHip];
      const prevRightHip = previousLandmarks[IDX.rightHip];
      torsoMovement = (distance2D(leftHip, prevLeftHip) + distance2D(rightHip, prevRightHip)) * 0.5;

      leftLegMovement = distance2D(leftAnkle, previousLandmarks[IDX.leftAnkle]);
      rightLegMovement = distance2D(rightAnkle, previousLandmarks[IDX.rightAnkle]);
    }

    smoothedHeadEnergy = smoothValue(smoothedHeadEnergy, clamp01(headMovement / 0.03), 0.3);

    previousLandmarks = landmarks.map((point) => ({ ...point }));

    const leftLegScore = leftHip.y - leftAnkle.y;
    const rightLegScore = rightHip.y - rightAnkle.y;
    smoothedLeftLegScore = smoothValue(smoothedLeftLegScore, leftLegScore, 0.35);
    smoothedRightLegScore = smoothValue(smoothedRightLegScore, rightLegScore, 0.35);

    const leftLegHeight = classifyBand(smoothedLeftLegScore, 0.11, 0.25, {
      low: 'LOW',
      mid: 'MID',
      high: 'HIGH',
    });
    const rightLegHeight = classifyBand(smoothedRightLegScore, 0.11, 0.25, {
      low: 'LOW',
      mid: 'MID',
      high: 'HIGH',
    });

    const energyRaw = movementRaw * 330;
    smoothedEnergy = smoothValue(smoothedEnergy, energyRaw, 0.25);
    const energyLevel = classifyBand(smoothedEnergy, 8, 20, {
      low: 'LOW',
      mid: 'MEDIUM',
      high: 'HIGH',
    });

    smoothedLeftLegMovement = smoothValue(smoothedLeftLegMovement, leftLegMovement * 220, 0.3);
    smoothedRightLegMovement = smoothValue(smoothedRightLegMovement, rightLegMovement * 220, 0.3);

    const leftArmMotionNorm = clamp01(leftArmMovement / 0.03);
    const rightArmMotionNorm = clamp01(rightArmMovement / 0.03);
    const leftArmHeightNorm = clamp01((smoothedLeftArmScore - 0.03) / 0.2);
    const rightArmHeightNorm = clamp01((smoothedRightArmScore - 0.03) / 0.2);

    const leftLegMotionNorm = clamp01(leftLegMovement / 0.025);
    const rightLegMotionNorm = clamp01(rightLegMovement / 0.025);
    const leftLegHeightNorm = clamp01((smoothedLeftLegScore - 0.08) / 0.22);
    const rightLegHeightNorm = clamp01((smoothedRightLegScore - 0.08) / 0.22);

    smoothedLeftArmIntensity = smoothValue(
      smoothedLeftArmIntensity,
      clamp01(leftArmMotionNorm * 0.58 + leftArmHeightNorm * 0.42),
      0.3
    );
    smoothedRightArmIntensity = smoothValue(
      smoothedRightArmIntensity,
      clamp01(rightArmMotionNorm * 0.58 + rightArmHeightNorm * 0.42),
      0.3
    );
    smoothedLeftLegIntensity = smoothValue(
      smoothedLeftLegIntensity,
      clamp01(leftLegMotionNorm * 0.62 + leftLegHeightNorm * 0.38),
      0.3
    );
    smoothedRightLegIntensity = smoothValue(
      smoothedRightLegIntensity,
      clamp01(rightLegMotionNorm * 0.62 + rightLegHeightNorm * 0.38),
      0.3
    );

    const hands = {
      left: { detected: false, gesture: null, emoji: '', score: -1 },
      right: { detected: false, gesture: null, emoji: '', score: -1 },
    };

    for (let i = 0; i < handLandmarks.length; i += 1) {
      const landmarksForHand = handLandmarks[i];
      const label = handednessLabel(handHandednesses[i]);
      if (!label || !hands[label]) {
        continue;
      }

      const score = handHandednesses[i]?.[0]?.score ?? 0;
      if (score < hands[label].score) {
        continue;
      }

      const detection = handGestureFromLandmarks(landmarksForHand, previousHandOpenness[label]);
      previousHandOpenness[label] = detection.openness;

      hands[label] = {
        detected: true,
        gesture: detection.key,
        emoji: detection.key ? HAND_GESTURE_EMOJI[detection.key] ?? '' : '',
        score,
      };
    }

    if (!hands.left.detected) {
      previousHandOpenness.left = NaN;
    }
    if (!hands.right.detected) {
      previousHandOpenness.right = NaN;
    }

    return {
      fps,
      energy: {
        level: energyLevel,
        value: Number(smoothedEnergy.toFixed(2)),
      },
      openness: {
        level: opennessLevel,
        value: Number(smoothedOpeness.toFixed(3)),
      },
      rotation: {
        direction: rotationDirection,
        value: Number(smoothedRotation.toFixed(3)),
      },
      leftArm: {
        wristX: Number(leftWrist.x.toFixed(3)),
        wristY: Number(leftWrist.y.toFixed(3)),
        height: leftArmHeight,
      },
      rightArm: {
        wristX: Number(rightWrist.x.toFixed(3)),
        wristY: Number(rightWrist.y.toFixed(3)),
        height: rightArmHeight,
      },
      leftLeg: {
        x: Number(leftAnkle.x.toFixed(3)),
        y: Number(leftAnkle.y.toFixed(3)),
        height: leftLegHeight,
        movement: Number(smoothedLeftLegMovement.toFixed(3)),
      },
      rightLeg: {
        x: Number(rightAnkle.x.toFixed(3)),
        y: Number(rightAnkle.y.toFixed(3)),
        height: rightLegHeight,
        movement: Number(smoothedRightLegMovement.toFixed(3)),
      },
      partActivity: {
        head: headMovement > 0.008,
        leftArm: leftArmMovement > 0.014,
        rightArm: rightArmMovement > 0.014,
        torso: torsoMovement > 0.008,
        leftLeg: leftLegMovement > 0.01,
        rightLeg: rightLegMovement > 0.01,
      },
      limbIntensity: {
        leftArm: Number(smoothedLeftArmIntensity.toFixed(3)),
        rightArm: Number(smoothedRightArmIntensity.toFixed(3)),
        leftLeg: Number(smoothedLeftLegIntensity.toFixed(3)),
        rightLeg: Number(smoothedRightLegIntensity.toFixed(3)),
      },
      bodyMapVisual: {
        headEnergy: Number(smoothedHeadEnergy.toFixed(3)),
        openness: Number(clamp01(smoothedOpeness).toFixed(3)),
        torsoRotation: Number(smoothedRotation.toFixed(3)),
      },
      debugPoints: {
        nose: { x: nose.x, y: nose.y, z: nose.z },
        leftWrist: { x: leftWrist.x, y: leftWrist.y, z: leftWrist.z },
        rightWrist: { x: rightWrist.x, y: rightWrist.y, z: rightWrist.z },
        leftAnkle: { x: leftAnkle.x, y: leftAnkle.y, z: leftAnkle.z },
        rightAnkle: { x: rightAnkle.x, y: rightAnkle.y, z: rightAnkle.z },
      },
      face: {
        detected: faceDetected,
        smile: Number(smoothedFaceSmile.toFixed(2)),
        mouthOpen: Number(smoothedFaceMouthOpen.toFixed(2)),
        eyeOpen: Number(((smoothedFaceEyeOpenLeft + smoothedFaceEyeOpenRight) * 0.5).toFixed(2)),
        browRaise: Number(smoothedFaceBrowRaise.toFixed(2)),
        emoji: faceEmoji,
        partActivity: facePartActivity,
      },
      hands: {
        left: {
          detected: hands.left.detected,
          gesture: hands.left.gesture,
          emoji: hands.left.emoji,
        },
        right: {
          detected: hands.right.detected,
          gesture: hands.right.gesture,
          emoji: hands.right.emoji,
        },
      },
      landmarks,
    };
  };
}
