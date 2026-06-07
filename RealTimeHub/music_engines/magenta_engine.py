import importlib
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger('RealTimeHub.magenta_engine')


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class MagentaEngine:
    def __init__(self, use_mock: bool = False, update_interval: float = 0.5, model_size: str = 'mrt2_small') -> None:
        self.use_mock = use_mock
        self.available = False
        self.magenta_module = None
        self.model = None
        self.model_state = None
        self.last_update_ts = 0.0
        self.update_interval = update_interval
        self.model_size = model_size
        self.model_class_name = None
        self.paths = None
        self._load_module()

    def _load_module(self) -> None:
        if self.use_mock:
            logger.info('MagentaEngine: forced mock mode enabled.')
            return

        try:
            self.magenta_module = importlib.import_module('magenta_rt')
            try:
                self.paths = importlib.import_module('magenta_rt.paths')
            except Exception:
                self.paths = getattr(self.magenta_module, 'paths', None)
            logger.info('MagentaEngine: imported magenta_rt.')
        except ImportError:
            logger.error(
                'MagentaEngine: magenta_rt is not installed. Install magenta-rt[mlx] to enable MRT2 control.'
            )
            self.use_mock = True
            self.magenta_module = None
            self.paths = None

    def _select_model_class(self):
        if self.magenta_module is None:
            return None

        for candidate in ('MagentaRT2Mlxfn', 'MagentaRT2Mlx', 'MagentaRT2Jax'):
            model_class = getattr(self.magenta_module, candidate, None)
            if model_class is not None:
                self.model_class_name = candidate
                return model_class

        return None

    def connect(self) -> None:
        if self.use_mock:
            logger.info('MagentaEngine: running in mock mode; no real MRT2 engine will be created.')
            return

        if self.magenta_module is None:
            logger.error('MagentaEngine: cannot connect because magenta_rt module is unavailable.')
            self.use_mock = True
            return

        model_class = self._select_model_class()
        if model_class is None:
            logger.error(
                'MagentaEngine: no supported MRT2 runtime class found in magenta_rt; continuing in mock mode.'
            )
            self.use_mock = True
            return

        try:
            init_kwargs: Dict[str, Any] = {}
            if self.model_size:
                init_kwargs['size'] = self.model_size

            self.model = model_class(**init_kwargs)
            self.available = True
            logger.info('MagentaEngine: connected to local MRT2 model using %s size=%s.', self.model_class_name, self.model_size)
        except Exception as error:
            logger.exception('MagentaEngine: failed to initialize MRT2 model: %s', error)
            self.use_mock = True
            self.available = False
            self.model = None

    def _build_prompt(self, music_state: Dict[str, Any]) -> str:
        manual_prompt = str(music_state.get('manualPrompt') or '').strip()
        if manual_prompt:
            return manual_prompt

        prompt_parts = []
        density = _clamp(float(music_state.get('density', 0.0)))
        brightness = _clamp(float(music_state.get('brightness', 0.0)))
        tension = _clamp(float(music_state.get('tension', 0.0)))
        harmony_width = _clamp(float(music_state.get('harmonyWidth', 0.0)))
        gesture_event = str(music_state.get('gestureEvent', 'none'))
        prompt_hints = list(music_state.get('promptHints', []))

        if density > 0.7:
            prompt_parts.append('energetic groove')
        elif density > 0.35:
            prompt_parts.append('steady rhythmic pulse')
        else:
            prompt_parts.append('ambient slow texture')

        if brightness > 0.55:
            prompt_parts.append('bright open harmony')
        else:
            prompt_parts.append('dark spacious atmosphere')

        if tension > 0.5:
            prompt_parts.append('dramatic tension')

        if harmony_width > 0.6:
            prompt_parts.append('wide harmonic field')

        if prompt_hints:
            prompt_parts.extend([str(item) for item in prompt_hints if item])

        if gesture_event and gesture_event != 'none':
            prompt_parts.append(str(gesture_event).replace('_', ' '))

        return ' | '.join(prompt_parts)

    def _music_control_values(self, translated: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'temperature': 0.8 + translated['tension'] * 0.8,
            'top_k': max(1, min(80, 20 + int(translated['harmonyWidth'] * 30))),
            'cfg_musiccoca': max(0.1, 1.0 + translated['brightness'] * 3.0),
            'cfg_notes': max(0.1, 1.0 + translated['density'] * 2.0),
            'cfg_drums': max(0.1, 1.0 + translated['rhythmicActivity'] * 2.0),
            'frames': max(8, min(50, int(12 + translated['density'] * 38))),
        }

    def _should_update(self) -> bool:
        now = time.monotonic()
        if now - self.last_update_ts >= self.update_interval:
            self.last_update_ts = now
            return True
        return False

    def _translate_music_state(self, music_state: Dict[str, Any]) -> Dict[str, Any]:
        density = _clamp(float(music_state.get('density', 0.0)))
        brightness = _clamp(float(music_state.get('brightness', 0.0)))
        tension = _clamp(float(music_state.get('tension', 0.0)))
        rhythmic_activity = _clamp(float(music_state.get('rhythmicActivity', 0.0)))
        harmony_width = _clamp(float(music_state.get('harmonyWidth', 0.0)))
        gesture_event = str(music_state.get('gestureEvent', 'none'))
        prompt_hints = list(music_state.get('promptHints', []))

        prompt_text = self._build_prompt(music_state)
        if not prompt_text:
            prompt_text = 'dynamic music control'

        translated = {
            'density': density,
            'brightness': brightness,
            'tension': tension,
            'rhythmicActivity': rhythmic_activity,
            'harmonyWidth': harmony_width,
            'gestureEvent': gesture_event,
            'promptHints': prompt_hints,
            'promptText': prompt_text,
            'rawMusicState': {
                'density': density,
                'brightness': brightness,
                'tension': tension,
                'rhythmicActivity': rhythmic_activity,
                'harmonyWidth': harmony_width,
                'gestureEvent': gesture_event,
            },
        }

        logger.debug('MagentaEngine: translated musicState to MRT2 controls: %s', translated)
        logger.info(
            'MagentaEngine: control params density=%.3f brightness=%.3f tension=%.3f rhythmicActivity=%.3f harmonyWidth=%.3f gestureEvent=%s prompt=%s',
            density,
            brightness,
            tension,
            rhythmic_activity,
            harmony_width,
            gesture_event,
            prompt_text,
        )
        return translated

    def update_music_state(self, music_state: Dict[str, Any]) -> None:
        if not self._should_update():
            return

        translated = self._translate_music_state(music_state)

        if self.use_mock:
            logger.info('MagentaEngine (mock): update skipped; MRT2 unavailable.')
            return

        if not self.available:
            self.connect()

        if not self.available or self.model is None:
            logger.error('MagentaEngine: MRT2 engine is unavailable; continuing without audio output.')
            self.use_mock = True
            return

        try:
            style_embedding = self.model.embed_style(translated['promptText'], use_mapper=True)
            control_values = self._music_control_values(translated)

            wav, state = self.model.generate(
                style=style_embedding,
                cfg_musiccoca=control_values['cfg_musiccoca'],
                cfg_notes=control_values['cfg_notes'],
                cfg_drums=control_values['cfg_drums'],
                temperature=control_values['temperature'],
                top_k=control_values['top_k'],
                frames=control_values['frames'],
                state=self.model_state,
            )

            self.model_state = state

            if self.paths is not None and hasattr(self.paths, 'outputs_dir'):
                output_dir = self.paths.outputs_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                file_path = output_dir / f'mrt2_update_{int(time.time())}.wav'
                wav.write(str(file_path))
                logger.info(
                    'MagentaEngine: generated audio artifact %s (%.2fs, %d samples).',
                    file_path.name,
                    wav.seconds,
                    wav.num_samples,
                )
            else:
                logger.info('MagentaEngine: generated waveform (%.2fs, %d samples).', wav.seconds, wav.num_samples)
        except Exception as error:
            logger.exception('MagentaEngine: error while generating MRT2 audio: %s', error)
            self.use_mock = True

    def generate_test_audio(self, duration_seconds: float = 4.0) -> Optional[str]:
        if self.use_mock:
            logger.info('MagentaEngine: mock mode active, cannot generate Magenta audio.')
            return None

        if not self.available or self.model is None:
            self.connect()

        if not self.available or self.model is None:
            logger.error('MagentaEngine: MRT2 engine is unavailable; test generation skipped.')
            self.use_mock = True
            return None

        prompt = 'play a short cinematic dance groove with light harmonic motion'
        style_embedding = self.model.embed_style(prompt, use_mapper=True)
        frames = max(1, int(duration_seconds * 25))

        try:
            wav, _ = self.model.generate(style=style_embedding, frames=frames)
            if self.paths is not None and hasattr(self.paths, 'outputs_dir'):
                output_dir = self.paths.outputs_dir()
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / 'test_mrt2_realtimehub.wav'
                wav.write(str(output_path))
                logger.info('MagentaEngine: test audio saved to %s', output_path)
                return str(output_path)
            logger.info('MagentaEngine: generated test audio successfully.')
            return None
        except Exception as error:
            logger.exception('MagentaEngine: failed to generate test audio: %s', error)
            self.use_mock = True
            return None

    def shutdown(self) -> None:
        if self.model is None:
            logger.info('MagentaEngine: no MRT2 model to shut down.')
            return

        if hasattr(self.model, 'shutdown'):
            try:
                self.model.shutdown()
                logger.info('MagentaEngine: MRT2 model shutdown complete.')
            except Exception as error:
                logger.exception('MagentaEngine: error during MRT2 shutdown: %s', error)
        else:
            logger.info('MagentaEngine: MRT2 model has no explicit shutdown method.')

        self.model = None
        self.available = False
        self.model_state = None
