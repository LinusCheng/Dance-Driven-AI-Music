import importlib
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger('backend.magenta')


class MagentaController:
    def __init__(self, mock: bool = False) -> None:
        self.mock = mock
        self.connected = False
        self.last_update_ts = 0.0
        self.update_interval = 0.5
        self.magenta_module = None
        self.model = None
        self._load_magenta()

    def _load_magenta(self) -> None:
        if self.mock:
            logger.info('MagentaController: forced mock mode enabled.')
            return

        try:
            self.magenta_module = importlib.import_module('magenta_rt')
            logger.info('MagentaController: magenta_rt module imported.')
        except ImportError:
            logger.warning('MagentaController: magenta_rt package not installed; falling back to mock mode.')
            self.mock = True
            return

        if not hasattr(self.magenta_module, '__name__'):
            logger.warning('MagentaController: magenta_rt module missing expected attributes; using mock mode.')
            self.mock = True
            self.magenta_module = None

    def connect(self) -> None:
        if self.mock:
            logger.info('MagentaController: running in mock mode; no real connection established.')
            return

        if self.magenta_module is None:
            logger.warning('MagentaController: magenta_rt module not available; mock mode enabled.')
            self.mock = True
            return

        try:
            # TODO: Update this if the magenta_rt package exposes a different runtime class.
            model_class = getattr(self.magenta_module, 'RealTimeModel', None)
            if model_class is None:
                model_class = getattr(self.magenta_module, 'RealtimeModel', None)

            if model_class is None:
                logger.warning('MagentaController: no supported model class found in magenta_rt; switching to mock mode.')
                self.mock = True
                return

            self.model = model_class()
            self.connected = True
            logger.info('MagentaController: connected to Magenta RT2 runtime.')
        except Exception as error:
            logger.exception('MagentaController: failed to initialize Magenta model: %s', error)
            self.mock = True
            self.model = None

    def _build_prompt(self, music_state: Dict[str, Any]) -> str:
        prompt_parts = []
        energy = float(music_state.get('density', 0.0))
        brightness = float(music_state.get('brightness', 0.0))
        tension = float(music_state.get('tension', 0.0))
        harmony_width = float(music_state.get('harmonyWidth', 0.0))

        if energy > 0.65:
            prompt_parts.append('energetic rhythm')
        elif energy > 0.3:
            prompt_parts.append('moving rhythm')
        else:
            prompt_parts.append('ambient sparse texture')

        if brightness > 0.55:
            prompt_parts.append('bright open harmony')
        else:
            prompt_parts.append('dark spacious harmony')

        if tension > 0.5:
            prompt_parts.append('dramatic tension')

        if harmony_width > 0.6:
            prompt_parts.append('wide harmonic field')

        if music_state.get('promptHints'):
            prompt_parts.extend([str(item) for item in music_state['promptHints'] if item])

        return ' | '.join(prompt_parts)

    def _should_send_update(self) -> bool:
        now = time.monotonic()
        if now - self.last_update_ts >= self.update_interval:
            self.last_update_ts = now
            return True
        return False

    def update_music_state(self, music_state: Dict[str, Any]) -> None:
        if not self._should_send_update():
            return

        prompt = self._build_prompt(music_state)
        if self.mock:
            logger.info('MagentaController (mock): would update with prompt: %s', prompt)
            logger.debug('MagentaController (mock): musicState=%s', music_state)
            return

        if not self.connected:
            self.connect()

        if not self.connected or self.model is None:
            logger.warning('MagentaController: not connected, skipping Magenta update.')
            return

        try:
            if hasattr(self.model, 'update'):
                self.model.update({'prompt': prompt, 'musicState': music_state})
                logger.info('MagentaController: updated model with prompt: %s', prompt)
            elif hasattr(self.model, 'send'):
                self.model.send({'prompt': prompt, 'musicState': music_state})
                logger.info('MagentaController: sent music state to Magenta model.')
            else:
                logger.warning('MagentaController: connected Magenta model does not support update/send; mock mode active.')
                self.mock = True
        except Exception as error:
            logger.exception('MagentaController: failed updating Magenta model: %s', error)
            self.mock = True

    def generate_test_audio(self, duration_seconds: float = 4.0) -> None:
        prompt = 'test tone with simple rhythmic texture'
        if self.mock:
            logger.info('MagentaController: mock mode active, cannot generate Magenta audio.')
            logger.info('Install magenta-rt[mlx] and required models to enable real Magenta generation.')
            return

        if not self.connected or self.model is None:
            self.connect()

        if not self.connected or self.model is None:
            logger.warning('MagentaController: generate_test_audio skipped because Magenta is unavailable.')
            return

        try:
            # TODO: If the actual MRT2 package exposes a named generator or session API,
            # wire it here instead of assuming generate() or generate_audio().
            if hasattr(self.model, 'generate'):
                result = self.model.generate(prompt=prompt, duration=duration_seconds)
                logger.info('MagentaController: generate_test_audio result: %s', result)
            elif hasattr(self.magenta_module, 'generate_audio'):
                result = self.magenta_module.generate_audio(prompt, duration_seconds)
                logger.info('MagentaController: generate_test_audio result: %s', result)
            else:
                logger.warning('MagentaController: no supported audio generation method found in magenta_rt.')
        except Exception as error:
            logger.exception('MagentaController: failed to generate test audio: %s', error)
            logger.info('MagentaController: continuing in mock mode.')
            self.mock = True

    def shutdown(self) -> None:
        if self.mock:
            logger.info('MagentaController: shutdown mock mode.')
            return

        if self.connected:
            logger.info('MagentaController: shutting down Magenta controller.')
        else:
            logger.info('MagentaController: shutdown called with no live Magenta connection.')
        self.connected = False
        self.model = None
