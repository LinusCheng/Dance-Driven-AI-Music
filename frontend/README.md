# Dance-Driven-AI-Music

An innovative web application that combines AI music generation with dance tracking and visualization.

## Features

- 🎵 AI-powered music generation and analysis
- 💃 Real-time dance tracking and metrics
- 📊 Interactive visualization and drawing capabilities
- 🎯 Performance counter and UI controls

## Project Structure

```
src/
├── main.js          # Main application entry point
├── counter.js       # Performance counter
├── drawing.js       # Visualization and drawing utilities
├── metrics.js       # Metrics tracking and analysis
├── tracker.js       # Dance/motion tracking
├── ui.js            # UI components and interactions
└── style.css        # Styling
public/              # Static assets
index.html           # Main HTML file
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/LinusCheng/Dance-Driven-AI-Music.git
cd Dance-Driven-AI-Music
```

2. Install dependencies:
```bash
npm install
```

3. Start the application:
```bash
npm run dev
```

## Running with GenMusicHub

By default the frontend connects to the GenMusicHub WebSocket at `ws://localhost:8765`.

To develop with real-time music, start GenMusicHub first (see `../GenMusicHub/README.md`) and then run `npm run dev` in this folder.

If you want to use the frontend standalone for UI development, open `index.html` in a browser, but the music features require GenMusicHub.

## Running with SunoHub

The Suno loop panel connects to SunoHub at `http://127.0.0.1:8000`. It only sends explicit text prompts when you click Generate; it does not consume motion data.

Start SunoHub in another terminal:

```bash
cd ../SunoHub
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Set `SUNO_API_KEY` in `SunoHub/.env` before generating clips.

## Offline / network requirements

The tracker uses MediaPipe Tasks Vision and normally downloads model assets and WASM support files from the web. Without internet, the tracker will fail with an error like:

`Tracker startup failed: pose failed to initialize (GPU: Failed to fetch; CPU: Failed to fetch)`

### Offline support

This project now supports offline loading if you host the required files locally under `public/`.

1. Install dependencies and copy the MediaPipe WASM runtime:

```bash
cd frontend
npm install
npm run prepare-offline
```

2. This will copy WASM runtime files to `public/mediapipe/wasm` and download the required model assets into `public/models`.

3. Start the frontend normally:

```bash
npm run dev
```

4. If you already have the model files locally and want to skip downloading them, you can still copy the runtime files manually and place the `.task` files into `frontend/public/models`.

The tracker code now prefers local WASM and model assets when they are available, and falls back to remote downloads only if the local files are missing.

## Usage

Open `index.html` in your web browser to start using the application.

## Dependencies

See `package.json` for a complete list of dependencies.

## Contributing

Feel free to fork and submit pull requests.

## License

MIT License

## Author

Created with ❤️
