import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any, Optional

import websockets

from dance_state import validate_and_normalize
from gesture_sequence import GestureSequenceDetector
from music_engines.magenta_engine import MagentaEngine
from music_mapper import dance_to_music_state
from smoothing import ExponentialSmoother

LOG_FORMAT = '[GenMusicHub] %(asctime)s %(levelname)s: %(message)s'
LOG_DATE_FORMAT = '%H:%M:%S'


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


logger = logging.getLogger('GenMusicHub')

latest_dance_state: dict[str, Any] = {}
latest_music_state: dict[str, Any] = {}
magenta_motion_input_enabled = False
magenta_model_size = 'small'

MAGENTA_MODEL_SIZES = {
    'small': 'mrt2_small',
    'base': 'mrt2_base',
}

smoother = ExponentialSmoother(alpha=0.32)
gesture_sequence_detector = GestureSequenceDetector()
magenta_engine: Optional[MagentaEngine] = None
last_feature_log_ts = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='GenMusicHub WebSocket bridge for danceState and Magenta RT2.')
    parser.add_argument('--mock-magenta', action='store_true', help='Force mock Magenta mode.')
    parser.add_argument('--test-magenta', action='store_true', help='Run a short Magenta test and exit.')
    parser.add_argument('--engine', default='mrt2', help='Music engine: "mrt2" (realtime, default) or "batch" (WAV files).')
    parser.add_argument('--model-size', choices=('small', 'base'), default='small', help='Magenta RT2 model size to load.')
    parser.add_argument('--verbose', action='store_true', help='Show full dance/music payloads and engine diagnostics.')
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers = [stdout_handler, stderr_handler]

    logging.getLogger('GenMusicHub.mrt2_realtime').setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('GenMusicHub.magenta_engine').setLevel(logging.DEBUG if verbose else logging.INFO)


def log_feature_summary(dance_state: dict[str, Any], music_state: dict[str, Any], interval_seconds: float = 1.0) -> None:
    global last_feature_log_ts

    now = time.monotonic()
    if now - last_feature_log_ts < interval_seconds:
        return

    last_feature_log_ts = now
    logger.info(
        'features energy=%.2f openness=%.2f rotation=%.2f smile=%.2f mouth=%.2f '
        'arms=%s/%s gestures=%s/%s -> music density=%.2f brightness=%.2f tension=%.2f genre=%s bpm=%s event=%s',
        float(dance_state.get('energy', 0.0)),
        float(dance_state.get('openness', 0.0)),
        float(dance_state.get('rotation', 0.0)),
        float(dance_state.get('smile', 0.0)),
        float(dance_state.get('mouthOpen', 0.0)),
        dance_state.get('leftArmHeight', 'LOW'),
        dance_state.get('rightArmHeight', 'LOW'),
        dance_state.get('gestureLeft', 'none'),
        dance_state.get('gestureRight', 'none'),
        float(music_state.get('density', 0.0)),
        float(music_state.get('brightness', 0.0)),
        float(music_state.get('tension', 0.0)),
        music_state.get('genre', 'adaptive'),
        music_state.get('bpm', '--'),
        music_state.get('gestureEvent', 'none'),
    )


def build_prompt_only_music_state(prompt: str) -> dict[str, Any]:
    prompt = prompt.strip()
    return {
        'density': 0.35,
        'brightness': 0.65,
        'tension': 0.12,
        'rhythmicActivity': 0.35,
        'harmonyWidth': 0.65,
        'genre': 'manual',
        'bpm': 120,
        'gestureEvent': 'none',
        'manualPrompt': prompt,
        'promptHints': [prompt] if prompt else [],
    }


def model_name_for_size(size: str) -> str:
    return MAGENTA_MODEL_SIZES.get(size, MAGENTA_MODEL_SIZES['small'])


def build_debug_payload(dance_state: dict[str, Any], music_state: dict[str, Any]) -> dict[str, Any]:
    engine_state = {}
    if magenta_engine is not None and hasattr(magenta_engine, 'get_debug_state'):
        try:
            engine_state = magenta_engine.get_debug_state()
        except Exception as error:
            logger.debug('Unable to read music engine debug state: %s', error)

    return {
        'type': 'backendDebug',
        'features': {
            'rawEnergy': round(float(dance_state.get('energy', 0.0)), 2),
            'openness': round(float(dance_state.get('openness', 0.0)), 2),
            'rotation': round(float(dance_state.get('rotation', 0.0)), 2),
            'smile': round(float(dance_state.get('smile', 0.0)), 2),
            'mouthOpen': round(float(dance_state.get('mouthOpen', 0.0)), 2),
            'arms': f"{dance_state.get('leftArmHeight', 'LOW')}/{dance_state.get('rightArmHeight', 'LOW')}",
            'gestures': f"{dance_state.get('gestureLeft', 'none')}/{dance_state.get('gestureRight', 'none')}",
        },
        'music': {
            'density': round(float(music_state.get('density', 0.0)), 2),
            'brightness': round(float(music_state.get('brightness', 0.0)), 2),
            'tension': round(float(music_state.get('tension', 0.0)), 2),
            'rhythm': round(float(music_state.get('rhythmicActivity', 0.0)), 2),
            'width': round(float(music_state.get('harmonyWidth', 0.0)), 2),
            'event': music_state.get('gestureEvent', 'none'),
            'genre': music_state.get('genre', 'adaptive'),
            'bpm': music_state.get('bpm'),
            'manualPrompt': music_state.get('manualPrompt', ''),
            'gestureSequence': music_state.get('gestureSequence'),
        },
        'mrt2': engine_state,
        'settings': {
            'magentaMotionInputEnabled': magenta_motion_input_enabled,
            'magentaModelSize': magenta_model_size,
            'magentaModelName': model_name_for_size(magenta_model_size),
        },
    }


def build_gesture_action_payload(action: dict[str, Any]) -> dict[str, Any]:
    return {
        'type': 'gestureAction',
        'action': action,
    }


async def maybe_send_debug_payload(
    websocket: Any,
    dance_state: dict[str, Any],
    music_state: dict[str, Any],
    last_sent_ts: float,
    interval_seconds: float = 1.0,
) -> float:
    now = time.monotonic()
    if now - last_sent_ts < interval_seconds:
        return last_sent_ts

    await websocket.send(json.dumps(build_debug_payload(dance_state, music_state)))
    return now


async def handle_connection(websocket: Any) -> None:
    global magenta_motion_input_enabled, magenta_model_size

    client_address = websocket.remote_address
    backend_debug_enabled = False
    last_debug_send_ts = 0.0
    manual_prompt = ''
    logger.info('Frontend connected: %s', client_address)

    try:
        async for raw_message in websocket:
            if not isinstance(raw_message, str):
                logger.warning('Received non-text payload; ignoring.')
                continue

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as error:
                logger.warning('Malformed JSON received: %s', error)
                continue

            if isinstance(payload, dict) and payload.get('type') == 'setBackendDebug':
                backend_debug_enabled = bool(payload.get('enabled'))
                last_debug_send_ts = 0.0
                await websocket.send(json.dumps({
                    'type': 'backendDebugStatus',
                    'enabled': backend_debug_enabled,
                }))
                continue

            if isinstance(payload, dict) and payload.get('type') == 'setMagentaMotionInput':
                magenta_motion_input_enabled = bool(payload.get('enabled'))
                if not magenta_motion_input_enabled and manual_prompt and magenta_engine is not None:
                    prompt_music_state = build_prompt_only_music_state(manual_prompt)
                    latest_music_state.update(prompt_music_state)
                    if hasattr(magenta_engine, 'last_update_ts'):
                        magenta_engine.last_update_ts = 0.0
                    magenta_engine.update_music_state(prompt_music_state)
                await websocket.send(json.dumps({
                    'type': 'magentaMotionInputStatus',
                    'enabled': magenta_motion_input_enabled,
                }))
                logger.info(
                    'Magenta motion input %s; %s',
                    'enabled' if magenta_motion_input_enabled else 'disabled',
                    'body motion controls Magenta' if magenta_motion_input_enabled else 'manual prompt controls Magenta only',
                )
                continue

            if isinstance(payload, dict) and payload.get('type') == 'setMagentaModelSize':
                requested_size = str(payload.get('size') or 'small').lower()
                if requested_size not in MAGENTA_MODEL_SIZES:
                    requested_size = 'small'
                magenta_model_size = requested_size
                model_name = model_name_for_size(magenta_model_size)
                if magenta_engine is not None and hasattr(magenta_engine, 'set_model_size'):
                    magenta_engine.set_model_size(model_name)
                await websocket.send(json.dumps({
                    'type': 'magentaModelSizeStatus',
                    'size': magenta_model_size,
                    'modelName': model_name,
                }))
                logger.info('Magenta model size set to %s (%s)', magenta_model_size, model_name)
                continue

            if isinstance(payload, dict) and payload.get('type') == 'setLiveControls':
                controls = payload.get('controls')
                if not isinstance(controls, dict):
                    controls = {}
                applied = False
                if magenta_engine is not None and hasattr(magenta_engine, 'update_live_controls'):
                    try:
                        magenta_engine.update_live_controls(controls)
                        applied = True
                    except (TypeError, ValueError) as error:
                        logger.warning('Invalid live controls payload: %s', error)
                await websocket.send(json.dumps({
                    'type': 'liveControlsStatus',
                    'applied': applied,
                    'controls': controls,
                }))
                logger.info('Live controls %s: %s', 'applied' if applied else 'ignored', controls)
                continue

            if isinstance(payload, dict) and payload.get('type') == 'setManualPrompt':
                manual_prompt = str(payload.get('prompt') or '').strip()[:280]
                prompt_music_state = (
                    build_prompt_only_music_state(manual_prompt)
                    if not magenta_motion_input_enabled
                    else dict(latest_music_state)
                )
                if magenta_motion_input_enabled:
                    prompt_music_state['manualPrompt'] = manual_prompt
                    prompt_music_state['promptHints'] = [manual_prompt] if manual_prompt else []
                latest_music_state.update(prompt_music_state)
                if magenta_engine is not None:
                    if hasattr(magenta_engine, 'last_update_ts'):
                        magenta_engine.last_update_ts = 0.0
                    magenta_engine.update_music_state(prompt_music_state)
                await websocket.send(json.dumps({
                    'type': 'manualPromptStatus',
                    'prompt': manual_prompt,
                    'enabled': bool(manual_prompt),
                }))
                logger.info('Manual Magenta prompt %s', 'set' if manual_prompt else 'cleared')
                continue

            try:
                dance_state = validate_and_normalize(payload)
            except ValueError as error:
                logger.warning('Invalid dance state payload: %s', error)
                continue

            smoothed = smoother.smooth_state(dance_state)
            style_state = gesture_sequence_detector.update(smoothed)
            style_state['manualPrompt'] = manual_prompt
            music_state = dance_to_music_state(smoothed, style_state)

            latest_dance_state.update(smoothed)
            latest_music_state.update(music_state)

            log_feature_summary(smoothed, music_state)
            logger.debug('danceState %s', smoothed)
            logger.debug('musicState %s', music_state)
            if magenta_engine is not None:
                if magenta_motion_input_enabled:
                    magenta_engine.update_music_state(music_state)
                elif hasattr(magenta_engine, 'update_motion_controls'):
                    magenta_engine.update_motion_controls(music_state)

            gesture_action = music_state.get('gestureSequence')
            if isinstance(gesture_action, dict):
                await websocket.send(json.dumps(build_gesture_action_payload(gesture_action)))
                logger.info('Gesture action sent to UI: %s', gesture_action.get('name', 'unknown'))

            if backend_debug_enabled:
                last_debug_send_ts = await maybe_send_debug_payload(
                    websocket,
                    smoothed,
                    music_state,
                    last_debug_send_ts,
                )

    except websockets.ConnectionClosedOK:
        logger.info('Frontend disconnected cleanly: %s', client_address)
    except websockets.ConnectionClosedError as error:
        logger.info('Frontend disconnected with error: %s', error)
    except Exception as error:
        logger.exception('Connection handler failed: %s', error)
    finally:
        logger.info('Frontend disconnected: %s', client_address)


async def run_server() -> None:
    global magenta_engine
    if magenta_engine is None:
        magenta_engine = MagentaEngine(use_mock=False)
    magenta_engine.connect()

    async with websockets.serve(handle_connection, '127.0.0.1', 8765):
        logger.info('WebSocket server listening on ws://localhost:8765')
        await asyncio.Future()


def main() -> int:
    global magenta_engine, magenta_model_size
    args = parse_args()
    configure_logging(args.verbose)
    magenta_model_size = args.model_size
    selected_model_name = model_name_for_size(magenta_model_size)

    # select engine implementation
    engine_name = args.engine
    if engine_name == 'mrt2':
        try:
            from music_engines.mrt2_realtime_engine import MRT2RealtimeEngine
            magenta_engine = MRT2RealtimeEngine(model_size=selected_model_name)
            magenta_engine.connect()
            magenta_engine.start_stream()
            logger.info('GenMusicHub: realtime MRT2 audio streaming enabled with model=%s', selected_model_name)
        except Exception as e:
            logger.exception('Failed to start MRT2RealtimeEngine: %s', e)
            logger.info('Falling back to batch mode (WAV generation)')
            magenta_engine = MagentaEngine(use_mock=args.mock_magenta, model_size=selected_model_name)
    else:
        # 'batch' mode or any other option
        magenta_engine = MagentaEngine(use_mock=args.mock_magenta, model_size=selected_model_name)
        if args.test_magenta:
            output_path = magenta_engine.generate_test_audio(duration_seconds=4.0)
            magenta_engine.shutdown()
            if output_path is not None:
                logger.info('Magenta test audio generated at %s', output_path)
            else:
                logger.info('Magenta test audio generation completed without an output file.')
            return 0

    try:
        asyncio.run(run_server())
        return 0
    except KeyboardInterrupt:
        logger.info('Shutting down GenMusicHub server.')
        if magenta_engine is not None:
            magenta_engine.shutdown()
        return 0
    except Exception as error:
        logger.exception('GenMusicHub failed: %s', error)
        if magenta_engine is not None:
            magenta_engine.shutdown()
        return 1


if __name__ == '__main__':
    sys.exit(main())
