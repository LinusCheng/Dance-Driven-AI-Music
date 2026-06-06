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
npm start
```

## Running with the backend

By default the frontend connects to a backend WebSocket at `ws://localhost:8765`.

To develop with real-time music, start the backend first (see `../backend/README.md`) and then run `npm start` in this folder.

If you want to use the frontend standalone for UI development, open `index.html` in a browser, but the music features require the backend.

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
