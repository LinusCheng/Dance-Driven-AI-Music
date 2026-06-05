import importlib
import logging
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger('backend.mrt2_realtime')

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

    def __init__(self, frames_per_chunk: int = 3, sample_rate: int = 16000, channels: int = 1):
        self.frames_per_chunk = int(frames_per_chunk)
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)

        self.magenta = None
        self.paths = None
        self.model = None
        self.model_state = None

        self._running = False
        self._gen_thread: Optional[threading.Thread] = None
        self._model_ready = threading.Event()  # signal when model is initialized in gen thread

        # audio buffer (numpy arrays, float32, shape (N, channels))
        self._buffer = deque()
        self._buffer_lock = threading.Lock()
        self._buffer_samples = 0

        # latest control / prompt state
        self._prompt = 'dynamic music control'
        self._style_embedding = None
        self._controls = {
            'cfg_musiccoca': 1.0,
            'cfg_notes': 1.0,
            'cfg_drums': 1.0,
            'temperature': 1.0,
            'top_k': 40,
        }
        self._target_controls = dict(self._controls)

        # sounddevice stream
        self._stream: Optional[sd.OutputStream] = None

        # underrun tracking
        self._underrun_count = 0

    def _select_runtime_class(self):
        for name in ('MagentaRT2Mlxfn', 'MagentaRT2Mlx', 'MagentaRT2Jax'):
            cls = getattr(self.magenta, name, None)
            if cls is not None:
                return cls, name
        return None, None

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
                logger.warning('MRT2RealtimeEngine: audio underrun [total=%d]', self._underrun_count)
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
                    if callback_count[0] - last_log_count[0] > 1 or buffer_before == 0:
                        logger.warning('MRT2RealtimeEngine: buffer underrun on callback #%d (had %d samples, need %d)', callback_count[0], buffer_before, needed)
                        last_log_count[0] = callback_count[0]

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

            cls, name = self._select_runtime_class()
            if cls is None:
                logger.error('MRT2RealtimeEngine: no supported MRT2 runtime class')
                self._running = False
                return

            init_kwargs: Dict[str, Any] = {}
            if self.paths is not None and hasattr(self.paths, 'DEFAULT_MODEL_NAME'):
                init_kwargs['size'] = self.paths.DEFAULT_MODEL_NAME

            logger.info('MRT2RealtimeEngine: creating runtime %s', name)
            self.model = cls(**init_kwargs)
            logger.info('MRT2RealtimeEngine: runtime instantiated: %s', type(self.model).__name__)

            # warm initial embedding
            try:
                self._style_embedding = self.model.embed_style(self._prompt, use_mapper=True)
                logger.info('MRT2RealtimeEngine: initial style embedding computed')
            except Exception as e:
                logger.error('MRT2RealtimeEngine: initial embed_style failed: %s', str(e))
                self._style_embedding = None

            self._model_ready.set()  # signal that model is ready
            logger.info('MRT2RealtimeEngine: model ready, starting generation loop')

            # ========== GENERATION LOOP ==========
            while self._running:
                # smooth control interpolation toward target
                for k, v in self._target_controls.items():
                    cur = self._controls.get(k, v)
                    self._controls[k] = cur + (v - cur) * 0.25

                # ensure style embedding is up to date if prompt changed
                try:
                    logger.debug('MRT2RealtimeEngine: embedding style prompt: %s', self._prompt)
                    self._style_embedding = self.model.embed_style(self._prompt, use_mapper=True)
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
                        logger.info('MRT2RealtimeEngine: generating %d frames (buffer %.2fs < %.2fs target)', frames, buf_secs, min_buffer_seconds)
                        logger.info('MRT2RealtimeEngine: calling model.generate with controls: %s', self._controls)
                        
                        wav, state = self.model.generate(
                            style=self._style_embedding,
                            cfg_musiccoca=self._controls.get('cfg_musiccoca'),
                            cfg_notes=self._controls.get('cfg_notes'),
                            cfg_drums=self._controls.get('cfg_drums'),
                            temperature=self._controls.get('temperature'),
                            top_k=int(self._controls.get('top_k', 40)),
                            frames=frames,
                            state=self.model_state,
                        )
                        self.model_state = state
                        gen_count += 1
                        fail_count = 0

                        # extract samples from Waveform
                        samples = np.array(wav.samples, dtype='float32')
                        logger.info('MRT2RealtimeEngine: model.generate returned %d samples with shape %s', len(samples), samples.shape)
                        
                        # convert stereo to mono if needed (take first channel)
                        if samples.ndim == 2 and samples.shape[1] > 1:
                            logger.info('MRT2RealtimeEngine: converting stereo to mono (taking first channel)')
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
                        logger.info('MRT2RealtimeEngine: generated chunk #%d: %d samples (peak=%.4f, buffer now %.2fs)', gen_count, samples.shape[0], peak, new_buf_secs)
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

    def update_music_state(self, music_state: Dict[str, Any]) -> None:
        # translate music_state to prompt and control values
        prompt_hints = music_state.get('promptHints', []) or []
        prompt_text = ' | '.join([str(p) for p in prompt_hints if p])
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

        self._prompt = prompt_text
        # target numeric controls
        self._target_controls['cfg_musiccoca'] = 1.0 + float(music_state.get('tension', 0.0)) * 2.0
        self._target_controls['cfg_notes'] = 1.0 + float(music_state.get('density', 0.0)) * 2.0
        self._target_controls['cfg_drums'] = 1.0 + float(music_state.get('rhythmicActivity', 0.0)) * 2.0
        self._target_controls['temperature'] = 0.8 + float(music_state.get('tension', 0.0)) * 0.8
        self._target_controls['top_k'] = max(1, min(80, 20 + int(float(music_state.get('harmonyWidth', 0.0)) * 30)))

        logger.info('MRT2RealtimeEngine: prompt updated: %s', self._prompt)

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
