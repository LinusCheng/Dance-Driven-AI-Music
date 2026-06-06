import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicModelsDir = path.join(__dirname, '../public/models');

const files = [
  {
    name: 'pose_landmarker_lite.task',
    url: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task',
  },
  {
    name: 'face_landmarker.task',
    url: 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
  },
  {
    name: 'hand_landmarker.task',
    url: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
  },
];

async function fetchFile(url, destination) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to download ${url}: ${res.status} ${res.statusText}`);
  }

  const buffer = await res.arrayBuffer();
  fs.writeFileSync(destination, Buffer.from(buffer));
  console.log(`Saved ${destination}`);
}

async function main() {
  fs.mkdirSync(publicModelsDir, { recursive: true });

  for (const file of files) {
    const dest = path.join(publicModelsDir, file.name);
    await fetchFile(file.url, dest);
  }

  console.log('Finished downloading MediaPipe model assets to public/models.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
