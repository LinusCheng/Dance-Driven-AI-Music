import importlib
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger('RealTimeHub.mrt2_realtime')


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _scale(value: float, source_min: float, source_max: float, target_min: float, target_max: float) -> float:
    if source_max == source_min:
        return target_min
    normalized = _clamp((value - source_min) / (source_max - source_min), 0.0, 1.0)
    return target_min + normalized * (target_max - target_min)


def _height_to_unit(height: Any) -> float:
    if isinstance(height, (int, float)):
        return _clamp(float(height), 0.0, 1.0)

    normalized = str(height or 'LOW').strip().upper()
    if normalized == 'HIGH':
        return 1.0
    if normalized == 'MID':
        return 0.5
    return 0.0


# helper: list available audio devices
def log_audio_devices():
    try:
        devices = sd.query_devices()
        logger.info('MRT2RealtimeEngine: available audio devices:')
        for i, dev in enumerate(devices):
            logger.info('  [%d] %s (channels: out=%d, in=%d)', i, dev['name'], dev['max_output_channels'], dev['max_input_channels'])
        default_out = sd.default.device[1]
        logger.info('MRT2RealtimeEngine: default output device: [%d] %s', default_out, devices[default_out]['name'])
    except Exception as e:
        logger.exception('MRT2RealtimeEngine: could not enumerate audio devices: %s', e)


class MRT2RealtimeEngine:
    """Realtime MRT2 engine: keeps model in memory and streams audio to speakers.

    Implementation notes:
    - Uses magenta_rt runtime (prefers MagentaRT2Mlxfn, then MagentaRT2Mlx, then MagentaRT2Jax).
    - Generates short audio chunks continuously and feeds an OutputStream callback.
    - Maintains persistent model state so generation is continuous.
    """

    def __init__(
        self,
        frames_per_chunk: int = 3,
        sample_rate: int = 48000,
        channels: int = 1,
        model_size: str = 'mrt2_small',
    ):
        self.frames_per_chunk = int(frames_per_chunk)
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.model_size = model_size
        self._requested_model_size = model_size

        self.magenta = None
        self.paths = None
        self.model = None
        self.model_state = None
        self._runtime_cls = None
        self._runtime_name = None

        self._running = False
        self._gen_thread: Optional[threading.Thread] = None
        self._model_ready = threading.Event()  # signal when model is initialized in gen thread

        # audio buffer (numpy arrays, float32, shape (N, channels))
        self._buffer = deque()
        self._buffer_lock = threading.Lock()
        self._buffer_samples = 0

        # latest control / prompt state
        self._prompt = 'dynamic music control'
        self._last_embedded_prompt = None
        self._prompt_changed = False
        self._style_embedding = None
        self._last_manual_prompt = ''
        self._controls = {
            'cfg_musiccoca': 1.0,
            'cfg_notes': 1.0,
            'cfg_drums': 1.0,
            'temperature': 1.0,
            'top_k': 40,
        }
        self._target_controls = dict(self._controls)
        self._controls_lock = threading.Lock()
        self._last_control_log_ts = 0.0

        # sounddevice stream
        self._stream: Optional[sd.OutputStream] = None

        # underrun tracking
        self._underrun_count = 0
        self._last_underrun_log_ts = 0.0
        self._last_model_load_error_ts = 0.0

    def _select_runtime_class(self):
        for name in ('MagentaRT2Mlxfn', 'MagentaRT2Mlx', 'MagentaRT2Jax'):
            cls = getattr(self.magenta, name, None)
            if cls is not None:
                return cls, name
        return None, None

    def _shutdown_model_only(self) -> None:
        if self.model is not None and hasattr(self.model, 'shutdown'):
            try:
                self.model.shutdown()
            except Exception:
                logger.exception('MRT2RealtimeEngine: error shutting down current model')

    def _model_file_exists(self, model_size: str) -> bool:
        if self.paths is None or not hasattr(self.paths, 'models_dir'):
            return True

        model_path = Path(self.paths.models_dir()) / model_size / f'{model_size}.mlxfn'
        return model_path.exists()

    def _maybe_fallback_to_base(self, missing_model: str) -> bool:
        fallback = 'mrt2_base'
        if missing_model == fallback or not self._model_file_exists(fallback):
            return False

        logger.warning(
            'MRT2RealtimeEngine: requested model %s is missing; falling back to installed %s. '
            'Download the small realtime model with: mrt models download %s',
            missing_model,
            fallback,
            missing_model,
        )
        self._requested_model_size = fallback
        return True

    def _log_model_load_error(self, message: str, *args, with_traceback: bool = False) -> None:
        now = time.monotonic()
        if now - self._last_model_load_error_ts < 30.0:
            return

        self._last_model_load_error_ts = now
        if with_traceback:
            logger.exception(message, *args)
        else:
            logger.error(message, *args)

    def _load_requested_model(self) -> bool:
        requested = self._requested_model_size
        if self._runtime_cls is None:
            logger.error('MRT2RealtimeEngine: cannot load %s because runtime class is unavailable', requested)
            return False

        if not self._model_file_exists(requested):
            if self._maybe_fallback_to_base(requested):
                return False
            self._log_model_load_error(
                'MRT2RealtimeEngine: model file missing for %s. Run: mrt models download %s',
                requested,
                requested,
            )
            return False

        logger.info('MRT2RealtimeEngine: loading model size=%s runtime=%s', requested, self._runtime_name)
        try:
            next_model = self._runtime_cls(size=requested)
            next_style_embedding = next_model.embed_style(self._prompt, use_mapper=True)
        except Exception as e:
            self._log_model_load_error(
                'MRT2RealtimeEngine: failed to load model size=%s. '
                'If missing, run: mrt models download %s',
                requested,
                requested,
                with_traceback=True,
            )
            return False

        self._shutdown_model_only()
        self.model = next_model
        self.model_size = requested
        self.model_state = None
        self._style_embedding = next_style_embedding
        self._last_embedded_prompt = self._prompt
        self._prompt_changed = False
        self._clear_buffer()
        self._model_ready.set()
        logger.info('MRT2RealtimeEngine: model ready size=%s', self.model_size)
        return True

    def set_model_size(self, model_size: str) -> None:
        if model_size == self._requested_model_size:
            return

        logger.info('MRT2RealtimeEngine: model switch requested %s -> %s', self._requested_model_size, model_size)
        self._requested_model_size = model_size
        self._model_ready.clear()
        self._clear_buffer()

    def connect(self) -> None:
        """Defer model initialization to generation thread (MLX requires same thread)."""
        logger.info('MRT2RealtimeEngine: connect() called (model init deferred to gen thread)')

    def start_stream(self, min_buffer_seconds: float = 0.4) -> None:
        """Start audio stream. Model will be initialized in generation thread."""
        log_audio_devices()
        logger.info('MRT2RealtimeEngine: starting audio stream (target buffer %.2fs)', min_buffer_seconds)

        # audio callback pulls from buffer
        callback_count = [0]
        last_log_count = [0]

        def callback(outdata, frames, time_info, status):
            callback_count[0] += 1
            if status.output_underflow:
                self._underrun_count += 1
                logger.debug('MRT2RealtimeEngine: audio underrun [total=%d]', self._underrun_count)
            if status.input_underflow:
                logger.warning('MRT2RealtimeEngine: input underflow')

            needed = frames
            out = np.zeros((frames, self.channels), dtype='float32')
            
            with self._buffer_lock:
                buffer_before = self._buffer_samples
                if self._buffer_samples >= needed:
                    read = 0
                    while read < needed and self._buffer:
                        chunk = self._buffer[0]
                        take = min(len(chunk), needed - read)
                        out[read:read+take] = chunk[:take]
                        if take == len(chunk):
                            self._buffer.popleft()
                        else:
                            self._buffer[0] = chunk[take:]
                        self._buffer_samples -= take
                        read += take
                else:
                    # not enough data — drain what we have
                    if self._buffer_samples > 0:
                        read = 0
                        while self._buffer and read < needed:
                            chunk = self._buffer[0]
                            take = min(len(chunk), needed - read)
                            out[read:read+take] = chunk[:take]
                            if take == len(chunk):
                                self._buffer.popleft()
                            else:
                                self._buffer[0] = chunk[take:]
                            self._buffer_samples -= take
                            read += take
                    # remaining frames are zero (silence)
                    now = time.monotonic()
                    if logger.isEnabledFor(logging.DEBUG) or now - self._last_underrun_log_ts >= 2.0:
                        logger.warning(
                            'MRT2RealtimeEngine: buffer underrun on callback #%d '
                            '(had %d samples, need %d, modelReady=%s, running=%s)',
                            callback_count[0],
                            buffer_before,
                            needed,
                            self._model_ready.is_set(),
                            self._running,
                        )
                        last_log_count[0] = callback_count[0]
                        self._last_underrun_log_ts = now

            outdata[:] = out
            if callback_count[0] % 100 == 0:
                logger.info('MRT2RealtimeEngine: callback #%d buffer_samples=%d peak=%.4f underruns=%d', callback_count[0], self._buffer_samples, np.abs(out).max(), self._underrun_count)

        # open output stream
        logger.info('MRT2RealtimeEngine: opening OutputStream (sample_rate=%d, channels=%d, dtype=float32)', self.sample_rate, self.channels)
        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='float32',
                callback=callback,
                latency='low',
                blocksize=2048,
            )
            self._stream.start()
        except Exception as e:
            logger.exception('MRT2RealtimeEngine: failed to start audio stream: %s', e)
            raise

        logger.info('MRT2RealtimeEngine: audio stream started')

        # start generation thread
        self._running = True
        self._gen_thread = threading.Thread(target=self._generate_loop, args=(min_buffer_seconds,), daemon=True, name='MRT2-GenLoop')
        self._gen_thread.start()
        logger.info('MRT2RealtimeEngine: generation thread started')

    def _append_buffer(self, samples: np.ndarray) -> None:
        # ensure shape (N, channels)
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)
        if samples.dtype != np.float32:
            samples = samples.astype('float32')
        with self._buffer_lock:
            self._buffer.append(samples)
            self._buffer_samples += samples.shape[0]

    def _current_buffer_seconds(self) -> float:
        return self._buffer_samples / float(self.sample_rate)

    def _clear_buffer(self) -> None:
        with self._buffer_lock:
            self._buffer.clear()
            self._buffer_samples = 0

    def _generate_loop(self, min_buffer_seconds: float) -> None:
        logger.info('MRT2RealtimeEngine: generate loop started (min_buffer=%.2fs)', min_buffer_seconds)
        gen_count = 0
        fail_count = 0
        
        try:
            # ========== INITIALIZE MODEL IN THIS THREAD (required for MLX) ==========
            logger.info('MRT2RealtimeEngine: initializing model in generation thread')
            try:
                self.magenta = importlib.import_module('magenta_rt')
                try:
                    self.paths = importlib.import_module('magenta_rt.paths')
                except Exception:
                    self.paths = getattr(self.magenta, 'paths', None)
                logger.info('MRT2RealtimeEngine: magenta_rt imported')
            except ImportError:
                logger.exception('MRT2RealtimeEngine: magenta_rt not installed')
                self._running = False
                return

            self._runtime_cls, self._runtime_name = self._select_runtime_class()
            if self._runtime_cls is None:
                logger.error('MRT2RealtimeEngine: no supported MRT2 runtime class')
                self._running = False
                return

            # ========== GENERATION LOOP ==========
            while self._running:
                if self.model is None or self.model_size != self._requested_model_size:
                    if not self._load_requested_model():
                        time.sleep(2.0)
                        continue

                # smooth control interpolation toward target
                with self._controls_lock:
                    for k, v in self._target_controls.items():
                        cur = self._controls.get(k, v)
                        self._controls[k] = cur + (v - cur) * 0.25
                    controls_snapshot = dict(self._controls)

                # ensure style embedding is up to date if prompt changed
                try:
                    if self._prompt_changed or self._style_embedding is None or self._prompt != self._last_embedded_prompt:
                        logger.debug('MRT2RealtimeEngine: embedding style prompt: %s', self._prompt)
                        self._style_embedding = self.model.embed_style(self._prompt, use_mapper=True)
                        self._last_embedded_prompt = self._prompt
                        self._prompt_changed = False
                        logger.debug('MRT2RealtimeEngine: style embedding computed')
                except Exception as e:
                    logger.error('MRT2RealtimeEngine: embed_style failed for prompt "%s": %s', self._prompt, str(e))
                    time.sleep(0.1)
                    continue

                # generate only if buffer is low
                buf_secs = self._current_buffer_seconds()
                if buf_secs < min_buffer_seconds:
                    try:
                        frames = self.frames_per_chunk
                        logger.debug('MRT2RealtimeEngine: generating %d frames (buffer %.2fs < %.2fs target)', frames, buf_secs, min_buffer_seconds)
                        logger.debug('MRT2RealtimeEngine: calling model.generate with controls: %s', controls_snapshot)
                        
                        wav, state = self.model.generate(
                            style=self._style_embedding,
                            cfg_musiccoca=controls_snapshot.get('cfg_musiccoca'),
                            cfg_notes=controls_snapshot.get('cfg_notes'),
                            cfg_drums=controls_snapshot.get('cfg_drums'),
                            temperature=controls_snapshot.get('temperature'),
                            top_k=int(controls_snapshot.get('top_k', 40)),
                            frames=frames,
                            state=self.model_state,
                        )
                        self.model_state = state
                        gen_count += 1
                        fail_count = 0

                        wav_sample_rate = int(getattr(wav, 'sample_rate', self.sample_rate))
                        if wav_sample_rate != self.sample_rate:
                            logger.warning(
                                'MRT2RealtimeEngine: resampling generated audio from %d Hz to stream rate %d Hz',
                                wav_sample_rate,
                                self.sample_rate,
                            )
                            if hasattr(wav, 'resample'):
                                wav = wav.resample(self.sample_rate)
                            else:
                                raise RuntimeError(
                                    f'Generated sample rate {wav_sample_rate} does not match stream rate {self.sample_rate}'
                                )

                        # extract samples from Waveform
                        samples = np.array(wav.samples, dtype='float32')
                        logger.debug('MRT2RealtimeEngine: model.generate returned %d samples with shape %s', len(samples), samples.shape)
                        
                        # convert stereo to mono if needed (take first channel)
                        if samples.ndim == 2 and samples.shape[1] > 1:
                            logger.debug('MRT2RealtimeEngine: converting stereo to mono (taking first channel)')
                            samples = samples[:, 0]
                        
                        # ensure shape (N, channels)
                        if samples.ndim == 1:
                            samples = samples.reshape(-1, 1)

                        # check for NaN/inf
                        if np.any(~np.isfinite(samples)):
                            logger.warning('MRT2RealtimeEngine: generated samples contain NaN/inf, replacing with zero')
                            samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)

                        # peak normalize to avoid clipping
                        peak = np.abs(samples).max()
                        if peak > 1.0:
                            logger.debug('MRT2RealtimeEngine: clipping detected (peak=%.4f), normalizing', peak)
                            samples = samples / (peak * 1.05)

                        self._append_buffer(samples)
                        new_buf_secs = self._current_buffer_seconds()
                        logger.debug('MRT2RealtimeEngine: generated chunk #%d: %d samples (peak=%.4f, buffer now %.2fs)', gen_count, samples.shape[0], peak, new_buf_secs)
                        if gen_count == 1 or gen_count % 10 == 0:
                            logger.info(
                                'MRT2RealtimeEngine: generated chunk #%d samples=%d peak=%.4f buffer=%.2fs',
                                gen_count,
                                samples.shape[0],
                                peak,
                                new_buf_secs,
                            )
                    except Exception as e:
                        fail_count += 1
                        logger.error('MRT2RealtimeEngine: generation failed (attempt %d): %s', fail_count, str(e))
                        logger.exception('MRT2RealtimeEngine: full traceback:')
                        if fail_count > 5:
                            logger.critical('MRT2RealtimeEngine: too many failures, stopping generation loop')
                            self._running = False
                            break
                        # avoid spin
                        time.sleep(0.1)
                else:
                    if gen_count % 10 == 0:
                        logger.debug('MRT2RealtimeEngine: buffer full (%.2fs), sleeping', buf_secs)
                    time.sleep(0.05)
        except Exception as e:
            logger.exception('MRT2RealtimeEngine: generate loop crashed: %s', str(e))
        finally:
            logger.info('MRT2RealtimeEngine: generate loop exiting (generated %d chunks, %d failures)', gen_count, fail_count)
            self._model_ready.set()  # ensure ready event is set even on failure

    def update_live_controls(self, controls: Dict[str, Any]) -> None:
        next_controls = {}

        if 'temperature' in controls:
            next_controls['temperature'] = _clamp(float(controls['temperature']), 0.5, 2.0)
        if 'top_k' in controls:
            next_controls['top_k'] = int(round(_clamp(float(controls['top_k']), 10.0, 500.0)))
        if 'cfg_musiccoca' in controls:
            next_controls['cfg_musiccoca'] = _clamp(float(controls['cfg_musiccoca']), 0.5, 5.0)
        if 'cfg_notes' in controls:
            next_controls['cfg_notes'] = _clamp(float(controls['cfg_notes']), 0.1, 6.0)
        if 'cfg_drums' in controls:
            next_controls['cfg_drums'] = _clamp(float(controls['cfg_drums']), 0.1, 6.0)

        if not next_controls:
            return

        with self._controls_lock:
            self._target_controls.update(next_controls)

        logger.info(
            'MRT2RealtimeEngine: live controls updated %s',
            ', '.join(f'{key}={value}' for key, value in next_controls.items()),
        )

    def update_motion_controls(self, music_state: Dict[str, Any]) -> None:
        self._apply_motion_controls(music_state, include_density_controls=False)

    def _apply_motion_controls(self, music_state: Dict[str, Any], include_density_controls: bool) -> None:
        right_height = _height_to_unit(music_state.get('rightArmHeight', 'LOW'))
        left_height = _height_to_unit(music_state.get('leftArmHeight', 'LOW'))
        live_motion_controls = {
            'cfg_musiccoca': _scale(left_height, 0.0, 1.0, 0.5, 5.0),
            'top_k': int(round(_scale(right_height, 0.0, 1.0, 10.0, 500.0))),
        }

        if include_density_controls:
            live_motion_controls.update({
                'cfg_notes': 1.0 + float(music_state.get('density', 0.0)) * 2.0,
                'cfg_drums': 1.0 + float(music_state.get('rhythmicActivity', 0.0)) * 2.0,
            })

        with self._controls_lock:
            self._target_controls.update(live_motion_controls)
            target_temperature = float(self._target_controls.get('temperature', 1.0))

        now = time.monotonic()
        if now - self._last_control_log_ts >= 1.0:
            logger.info(
                'MRT2RealtimeEngine: motion controls rightArm=%.2f -> top_k=%d, leftArm=%.2f -> cfg_musiccoca=%.2f, temperature=%.2f',
                right_height,
                live_motion_controls['top_k'],
                left_height,
                live_motion_controls['cfg_musiccoca'],
                target_temperature,
            )
            self._last_control_log_ts = now

    def update_music_state(self, music_state: Dict[str, Any]) -> None:
        # translate music_state to prompt and control values
        manual_prompt = str(music_state.get('manualPrompt') or '').strip()
        prompt_hints = music_state.get('promptHints', []) or []
        prompt_text = manual_prompt or ' | '.join([str(p) for p in prompt_hints if p])
        if not prompt_text:
            # simple mapping based on density/brightness
            d = float(music_state.get('density', 0.0))
            b = float(music_state.get('brightness', 0.0))
            if d > 0.7:
                prompt_text = 'energetic groove'
            elif d > 0.3:
                prompt_text = 'steady rhythmic pulse'
            else:
                prompt_text = 'ambient texture'
            if b > 0.6:
                prompt_text += ' | bright harmony'

        manual_prompt_changed = manual_prompt != self._last_manual_prompt
        prompt_changed = prompt_text != self._prompt
        self._prompt = prompt_text
        if prompt_changed:
            self._prompt_changed = True
            if manual_prompt_changed:
                self.model_state = None
                self._clear_buffer()
                logger.info('MRT2RealtimeEngine: manual prompt changed; reset model state and audio buffer')
            else:
                logger.info('MRT2RealtimeEngine: style prompt changed without clearing audio buffer')
        self._last_manual_prompt = manual_prompt
        self._apply_motion_controls(music_state, include_density_controls=True)

        logger.debug('MRT2RealtimeEngine: prompt updated: %s', self._prompt)

    def get_debug_state(self) -> Dict[str, Any]:
        with self._controls_lock:
            target_controls = dict(self._target_controls)
            current_controls = dict(self._controls)

        return {
            'prompt': self._prompt,
            'controls': {
                'cfgMusicCoca': round(float(target_controls.get('cfg_musiccoca', 0.0)), 3),
                'cfgNotes': round(float(target_controls.get('cfg_notes', 0.0)), 3),
                'cfgDrums': round(float(target_controls.get('cfg_drums', 0.0)), 3),
                'temperature': round(float(target_controls.get('temperature', 0.0)), 3),
                'topK': int(target_controls.get('top_k', 0)),
                'currentCfgMusicCoca': round(float(current_controls.get('cfg_musiccoca', 0.0)), 3),
                'currentTemperature': round(float(current_controls.get('temperature', 0.0)), 3),
                'currentTopK': int(current_controls.get('top_k', 0)),
            },
            'audio': {
                'bufferSeconds': round(self._current_buffer_seconds(), 2),
                'underruns': self._underrun_count,
                'running': self._running,
                'modelReady': self._model_ready.is_set(),
            },
            'model': {
                'size': self.model_size,
                'requestedSize': self._requested_model_size,
                'runtime': self._runtime_name,
            },
        }

    def shutdown(self) -> None:
        logger.info('MRT2RealtimeEngine: shutting down')
        self._running = False
        if self._gen_thread is not None:
            self._gen_thread.join(timeout=2.0)
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                logger.exception('MRT2RealtimeEngine: error closing audio stream')
        # model shutdown if supported
        if self.model is not None and hasattr(self.model, 'shutdown'):
            try:
                self.model.shutdown()
            except Exception:
                logger.exception('MRT2RealtimeEngine: error shutting down model')
