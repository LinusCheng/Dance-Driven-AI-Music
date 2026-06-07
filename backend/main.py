import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Any, Optional

import websockets

from config.logging_config import configure_logging
from core.dance_state import validate_and_normalize
from core.smoothing import ExponentialSmoother
from mapping.gesture_sequence import GestureSequenceDetector
from mapping.music_mapper import dance_to_music_state
from mapping.prompt_weights import (
    default_prompt_texts,
    default_prompt_weights,
    normalize_prompt_texts,
    normalize_prompt_weights,
)
from music_engines.cpp_engine_portal import CppEnginePortal


logger = logging.getLogger('Backend')

latest_dance_state: dict[str, Any] = {}
latest_music_state: dict[str, Any] = {}
engine_motion_input_enabled = False
engine_model_size = 'small'
prompt_weights = default_prompt_weights()
prompt_texts = default_prompt_texts()

MODEL_SIZES = {
    'small': 'mrt2_small',
    'base': 'mrt2_base',
}

smoother = ExponentialSmoother(alpha=0.32)
gesture_sequence_detector = GestureSequenceDetector()
cpp_engine: Optional[CppEnginePortal] = None
last_feature_log_ts = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backend WebSocket bridge for danceState and GenMusicEngine.')
    parser.add_argument('--engine-executable', default='GenMusicEngine/ninja-build/gen_music_engine', help='Path to GenMusicEngine executable.')
    parser.add_argument('--model-size', choices=('small', 'base'), default='small', help='Model size hint to pass to GenMusicEngine.')
    parser.add_argument('--host', default='127.0.0.1', help='WebSocket host.')
    parser.add_argument('--port', type=int, default=8766, help='WebSocket port. Use 8765 when replacing GenMusicHub.')
    parser.add_argument('--verbose', action='store_true', help='Show full dance/music payloads and portal diagnostics.')
    return parser.parse_args()


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
        'promptWeights': dict(prompt_weights),
    }


def model_name_for_size(size: str) -> str:
    return MODEL_SIZES.get(size, MODEL_SIZES['base'])


def build_debug_payload(dance_state: dict[str, Any], music_state: dict[str, Any]) -> dict[str, Any]:
    engine_state = {}
    if cpp_engine is not None and hasattr(cpp_engine, 'get_debug_state'):
        try:
            engine_state = cpp_engine.get_debug_state()
        except Exception as error:
            logger.debug('Unable to read engine debug state: %s', error)

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
            'promptWeights': music_state.get('promptWeights', {}),
        },
        'engine': engine_state,
        'settings': {
            'engineMotionInputEnabled': engine_motion_input_enabled,
            'engineModelSize': engine_model_size,
            'engineModelName': model_name_for_size(engine_model_size),
            'promptTexts': prompt_texts,
            'promptWeights': prompt_weights,
        },
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


def is_message_type(payload: Any, *message_types: str) -> bool:
    return isinstance(payload, dict) and payload.get('type') in message_types


async def handle_connection(websocket: Any) -> None:
    global engine_motion_input_enabled, engine_model_size, prompt_weights, prompt_texts

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

            if is_message_type(payload, 'setBackendDebug'):
                backend_debug_enabled = bool(payload.get('enabled'))
                last_debug_send_ts = 0.0
                await websocket.send(json.dumps({
                    'type': 'backendDebugStatus',
                    'enabled': backend_debug_enabled,
                }))
                continue

            if is_message_type(payload, 'setEngineMotionInput', 'setMagentaMotionInput'):
                engine_motion_input_enabled = bool(payload.get('enabled'))
                if not engine_motion_input_enabled and manual_prompt and cpp_engine is not None:
                    cpp_engine.update_music_state(build_prompt_only_music_state(manual_prompt))
                await websocket.send(json.dumps({
                    'type': 'engineMotionInputStatus',
                    'enabled': engine_motion_input_enabled,
                }))
                await websocket.send(json.dumps({
                    'type': 'magentaMotionInputStatus',
                    'enabled': engine_motion_input_enabled,
                }))
                logger.info(
                    'Engine motion input %s; %s',
                    'enabled' if engine_motion_input_enabled else 'disabled',
                    'body motion controls engine portal' if engine_motion_input_enabled else 'manual prompt controls engine portal only',
                )
                continue

            if is_message_type(payload, 'setEngineModelSize', 'setMagentaModelSize'):
                requested_size = str(payload.get('size') or 'base').lower()
                if requested_size not in MODEL_SIZES:
                    requested_size = 'base'
                engine_model_size = requested_size
                model_name = model_name_for_size(engine_model_size)
                if cpp_engine is not None:
                    cpp_engine.set_model_size(model_name)
                await websocket.send(json.dumps({
                    'type': 'engineModelSizeStatus',
                    'size': engine_model_size,
                    'modelName': model_name,
                }))
                await websocket.send(json.dumps({
                    'type': 'magentaModelSizeStatus',
                    'size': engine_model_size,
                    'modelName': model_name,
                }))
                logger.info('Engine model size set to %s (%s)', engine_model_size, model_name)
                continue

            if is_message_type(payload, 'setPromptWeights'):
                prompt_weights = normalize_prompt_weights(payload.get('weights'))
                if latest_music_state:
                    latest_music_state['promptWeights'] = dict(prompt_weights)
                    if cpp_engine is not None:
                        cpp_engine.update_music_state(latest_music_state)
                await websocket.send(json.dumps({
                    'type': 'promptWeightsStatus',
                    'weights': prompt_weights,
                }))
                logger.info('Prompt weights updated: %s', prompt_weights)
                continue

            if is_message_type(payload, 'setPromptNodes'):
                prompt_texts = normalize_prompt_texts(payload.get('promptTexts'))
                prompt_weights = normalize_prompt_weights(payload.get('weights'))
                if latest_music_state:
                    latest_music_state['promptWeights'] = dict(prompt_weights)
                if cpp_engine is not None:
                    cpp_engine.update_prompt_nodes(prompt_texts, prompt_weights)
                await websocket.send(json.dumps({
                    'type': 'promptNodesStatus',
                    'promptTexts': prompt_texts,
                    'weights': prompt_weights,
                }))
                logger.info('Prompt nodes updated texts=%s weights=%s', prompt_texts, prompt_weights)
                continue

            if is_message_type(payload, 'setLiveControls'):
                controls = payload.get('controls')
                if not isinstance(controls, dict):
                    controls = {}
                applied = False
                if cpp_engine is not None:
                    try:
                        cpp_engine.update_live_controls(controls)
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

            if is_message_type(payload, 'setManualPrompt'):
                manual_prompt = str(payload.get('prompt') or '').strip()[:280]
                prompt_music_state = (
                    build_prompt_only_music_state(manual_prompt)
                    if not engine_motion_input_enabled
                    else dict(latest_music_state)
                )
                if engine_motion_input_enabled:
                    prompt_music_state['manualPrompt'] = manual_prompt
                    prompt_music_state['promptHints'] = [manual_prompt] if manual_prompt else []
                    prompt_music_state['promptWeights'] = dict(prompt_weights)
                latest_music_state.update(prompt_music_state)
                if cpp_engine is not None:
                    cpp_engine.update_music_state(prompt_music_state)
                await websocket.send(json.dumps({
                    'type': 'manualPromptStatus',
                    'prompt': manual_prompt,
                    'enabled': bool(manual_prompt),
                }))
                logger.info('Manual prompt %s', 'set' if manual_prompt else 'cleared')
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
            music_state['promptWeights'] = dict(prompt_weights)

            latest_dance_state.update(smoothed)
            latest_music_state.update(music_state)

            log_feature_summary(smoothed, music_state)
            logger.debug('danceState %s', smoothed)
            logger.debug('musicState %s', music_state)
            if cpp_engine is not None:
                if engine_motion_input_enabled:
                    cpp_engine.update_music_state(music_state)
                else:
                    cpp_engine.update_motion_controls(music_state)

            gesture_action = music_state.get('gestureSequence')
            if isinstance(gesture_action, dict):
                await websocket.send(json.dumps({
                    'type': 'gestureAction',
                    'action': gesture_action,
                }))
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


async def run_server(host: str, port: int) -> None:
    global cpp_engine
    if cpp_engine is None:
        cpp_engine = CppEnginePortal()
    cpp_engine.connect()

    async with websockets.serve(handle_connection, host, port):
        logger.info('WebSocket server listening on ws://%s:%d', host, port)
        await asyncio.Future()


def main() -> int:
    global cpp_engine, engine_model_size
    args = parse_args()
    configure_logging(args.verbose)
    engine_model_size = args.model_size
    cpp_engine = CppEnginePortal(executable_path=args.engine_executable)
    cpp_engine.set_model_size(model_name_for_size(engine_model_size))

    try:
        asyncio.run(run_server(args.host, args.port))
        return 0
    except KeyboardInterrupt:
        logger.info('Shutting down Backend server.')
        if cpp_engine is not None:
            cpp_engine.shutdown()
        return 0
    except Exception as error:
        logger.exception('Backend failed: %s', error)
        if cpp_engine is not None:
            cpp_engine.shutdown()
        return 1


if __name__ == '__main__':
    sys.exit(main())
