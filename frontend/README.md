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
