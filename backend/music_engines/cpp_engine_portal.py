import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mapping.prompt_weights import default_prompt_texts, default_prompt_weights


logger = logging.getLogger('Backend.cpp_engine_portal')


class CppEnginePortal:
    def __init__(
        self,
        executable_path: str = 'GenMusicEngine/build/gen_music_engine',
        startup_timeout: float = 2.0,
    ) -> None:
        self.executable_path = executable_path
        self.startup_timeout = startup_timeout
        self.process: Optional[subprocess.Popen[str]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._last_response: Dict[str, Any] = {}
        self._last_prompt = 'dynamic music control'
        self._last_controls: Dict[str, Any] = {}
        self._last_weights = default_prompt_weights()
        self._prompt_texts = default_prompt_texts()
        self._connected = False

    def _resolve_executable(self) -> Optional[Path]:
        repo_root = Path(__file__).resolve().parents[2]
        configured = Path(self.executable_path)
        candidates = []

        if configured.is_absolute():
            candidates.append(configured)
        else:
            candidates.extend([
                repo_root / configured,
                Path.cwd() / configured,
            ])

        candidates.extend([
            repo_root / 'GenMusicEngine' / 'build' / 'gen_music_engine',
            repo_root / 'GenMusicEngine' / 'cmake-build-debug' / 'gen_music_engine',
        ])

        seen = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.exists():
                return resolved

        return candidates[0].resolve() if candidates else None

    def connect(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        executable = self._resolve_executable()
        if executable is None or not executable.exists():
            logger.warning(
                'CppEnginePortal: executable not found at %s. Build GenMusicEngine first.',
                executable,
            )
            self._connected = False
            return

        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._connected = True
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

        stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        stderr_thread.start()
        logger.info('CppEnginePortal: started GenMusicEngine at %s', executable)

    def _read_stdout(self) -> None:
        if self.process is None or self.process.stdout is None:
            return

        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._last_response = json.loads(line)
                logger.debug('CppEnginePortal: response %s', self._last_response)
            except json.JSONDecodeError:
                logger.info('CppEnginePortal: %s', line)

    def _read_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return

        for line in self.process.stderr:
            line = line.strip()
            if line:
                logger.warning('GenMusicEngine stderr: %s', line)

    def _send(self, message: Dict[str, Any]) -> None:
        if self.process is None or self.process.poll() is not None:
            self.connect()

        if self.process is None or self.process.stdin is None or self.process.poll() is not None:
            logger.debug('CppEnginePortal: skipped send because engine is unavailable: %s', message)
            self._connected = False
            return

        self.process.stdin.write(json.dumps(message, separators=(',', ':')) + '\n')
        self.process.stdin.flush()

    def update_music_state(self, music_state: Dict[str, Any]) -> None:
        manual_prompt = str(music_state.get('manualPrompt') or '').strip()
        prompt_hints = music_state.get('promptHints', []) or []
        prompt = manual_prompt or ' | '.join(str(item) for item in prompt_hints if item)
        if not prompt:
            prompt = self._last_prompt

        controls = {
            'density': float(music_state.get('density', 0.0)),
            'brightness': float(music_state.get('brightness', 0.0)),
            'tension': float(music_state.get('tension', 0.0)),
            'rhythmicActivity': float(music_state.get('rhythmicActivity', 0.0)),
            'harmonyWidth': float(music_state.get('harmonyWidth', 0.0)),
            'bpm': music_state.get('bpm'),
            'genre': music_state.get('genre', 'adaptive'),
        }
        weights = dict(music_state.get('promptWeights') or default_prompt_weights())

        self._last_prompt = prompt
        self._last_controls = controls
        self._last_weights = weights
        self._send({
            'type': 'updateMusicState',
            'timestamp': time.time(),
            'prompt': prompt,
            'controls': controls,
            'weights': weights,
            'promptTexts': self._prompt_texts,
        })

    def update_motion_controls(self, music_state: Dict[str, Any]) -> None:
        self._send({
            'type': 'updateMotionControls',
            'timestamp': time.time(),
            'leftArmHeight': music_state.get('leftArmHeight', 'LOW'),
            'rightArmHeight': music_state.get('rightArmHeight', 'LOW'),
            'weights': dict(music_state.get('promptWeights') or self._last_weights),
            'promptTexts': self._prompt_texts,
        })

    def update_live_controls(self, controls: Dict[str, Any]) -> None:
        self._send({
            'type': 'updateLiveControls',
            'timestamp': time.time(),
            'controls': controls,
        })

    def set_model_size(self, model_name: str) -> None:
        self._send({
            'type': 'setModelSize',
            'timestamp': time.time(),
            'modelName': model_name,
        })

    def get_debug_state(self) -> Dict[str, Any]:
        return {
            'connected': self._connected,
            'executable': self.executable_path,
            'prompt': self._last_prompt,
            'controls': self._last_controls,
            'weights': self._last_weights,
            'promptTexts': self._prompt_texts,
            'lastResponse': self._last_response,
        }

    def shutdown(self) -> None:
        self._send({'type': 'shutdown', 'timestamp': time.time()})
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._connected = False
