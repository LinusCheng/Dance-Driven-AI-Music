const POSE_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 7], [0, 4], [4, 5], [5, 6], [6, 8],
  [9, 10], [11, 12], [11, 13], [13, 15], [15, 17], [15, 19], [15, 21],
  [17, 19], [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
  [11, 23], [12, 24], [23, 24], [23, 25], [24, 26], [25, 27], [26, 28],
  [27, 29], [28, 30], [29, 31], [30, 32], [27, 31], [28, 32],
];

function pointVisible(point) {
  return point && (point.visibility === undefined || point.visibility > 0.3);
}

export function createPoseDrawer(canvas) {
  const ctx = canvas.getContext('2d');
  let canvasWidth = 0;
  let canvasHeight = 0;

  function ensureSize(width, height) {
    if (canvasWidth !== width || canvasHeight !== height) {
      canvas.width = width;
      canvas.height = height;
      canvasWidth = width;
      canvasHeight = height;
    }
  }

  function clear() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function draw(landmarks, width, height) {
    if (!width || !height) {
      return;
    }

    ensureSize(width, height);
    clear();

    if (!landmarks) {
      return;
    }

    ctx.lineWidth = 2;
    ctx.strokeStyle = 'rgba(95, 232, 252, 0.72)';

    for (const [a, b] of POSE_CONNECTIONS) {
      const p1 = landmarks[a];
      const p2 = landmarks[b];

      if (!pointVisible(p1) || !pointVisible(p2)) {
        continue;
      }

      ctx.beginPath();
      ctx.moveTo(p1.x * width, p1.y * height);
      ctx.lineTo(p2.x * width, p2.y * height);
      ctx.stroke();
    }

    for (const point of landmarks) {
      if (!pointVisible(point)) {
        continue;
      }

      const x = point.x * width;
      const y = point.y * height;

      ctx.beginPath();
      ctx.fillStyle = 'rgba(255, 211, 108, 0.95)';
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  return { draw, clear };
}
