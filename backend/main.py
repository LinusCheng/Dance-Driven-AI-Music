import argparse
import asyncio
import json
import logging
import sys
from typing import Any, Optional

import websockets

from config.logging_config import configure_logging
from mapping.prompt_weights import (
    default_prompt_texts,
    default_prompt_weights,
    normalize_prompt_weights,
)
from music_engines.cpp_engine_portal import CppEnginePortal


logger = logging.getLogger('Backend')

MODEL_SIZES = {
    'small': 'mrt2_small',
    'base': 'mrt2_base',
}

engine_model_size = 'small'
prompt_texts = default_prompt_texts()
prompt_weights = default_prompt_weights()
cpp_engine: Optional[CppEnginePortal] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Audience prompt-weight bridge for GenMusicEngine.')
    parser.add_argument('--engine-executable', default='GenMusicEngine/ninja-build/gen_music_engine', help='Path to GenMusicEngine executable.')
    parser.add_argument('--model-size', choices=('small', 'base'), default='small', help='Model size hint to pass to GenMusicEngine.')
    parser.add_argument('--host', default='localhost', help='WebSocket host.')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket port.')
    parser.add_argument('--verbose', action='store_true', help='Show verbose portal diagnostics.')
    return parser.parse_args()


def model_name_for_size(size: str) -> str:
    return MODEL_SIZES.get(size, MODEL_SIZES['small'])


def is_message_type(payload: Any, *message_types: str) -> bool:
    return isinstance(payload, dict) and payload.get('type') in message_types


def build_debug_payload() -> dict[str, Any]:
    engine_state = {}
    if cpp_engine is not None:
        try:
            engine_state = cpp_engine.get_debug_state()
        except Exception as error:
            logger.debug('Unable to read engine debug state: %s', error)

    return {
        'type': 'backendDebug',
        'engine': engine_state,
        'settings': {
            'engineModelSize': engine_model_size,
            'engineModelName': model_name_for_size(engine_model_size),
            'promptTexts': prompt_texts,
            'promptWeights': prompt_weights,
        },
    }


async def send_debug_payload(websocket: Any) -> None:
    await websocket.send(json.dumps(build_debug_payload()))


async def handle_connection(websocket: Any) -> None:
    global engine_model_size, prompt_weights

    client_address = websocket.remote_address
    backend_debug_enabled = False
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
                await websocket.send(json.dumps({
                    'type': 'backendDebugStatus',
                    'enabled': backend_debug_enabled,
                }))
                if backend_debug_enabled:
                    await send_debug_payload(websocket)
                continue

            if is_message_type(payload, 'setEngineModelSize', 'setMagentaModelSize'):
                requested_size = str(payload.get('size') or 'small').lower()
                if requested_size not in MODEL_SIZES:
                    requested_size = 'small'
                engine_model_size = requested_size
                model_name = model_name_for_size(engine_model_size)
                if cpp_engine is not None:
                    cpp_engine.set_model_size(model_name)
                await websocket.send(json.dumps({
                    'type': 'engineModelSizeStatus',
                    'size': engine_model_size,
                    'modelName': model_name,
                }))
                logger.info('Engine model size set to %s (%s)', engine_model_size, model_name)
                if backend_debug_enabled:
                    await send_debug_payload(websocket)
                continue

            if is_message_type(payload, 'setPromptWeights'):
                prompt_weights = normalize_prompt_weights(payload.get('weights'))
                if cpp_engine is not None:
                    cpp_engine.update_prompt_nodes(prompt_texts, prompt_weights)
                await websocket.send(json.dumps({
                    'type': 'promptWeightsStatus',
                    'weights': prompt_weights,
                }))
                logger.info('Prompt weights normalized and applied: %s', prompt_weights)
                if backend_debug_enabled:
                    await send_debug_payload(websocket)
                continue

            # Future audience-frontend payload shape:
            # {
            #   "type": "setPromptNodes",
            #   "promptTexts": {"node_1": "..."},
            #   "weights": {"node_1": 1.0}
            # }
            # Prompt text updates are intentionally disabled for now. Keep
            # prompt text authority in mapping/prompt_weights.py until the
            # audience UI is ready for controlled text editing.

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
                if backend_debug_enabled:
                    await send_debug_payload(websocket)
                continue

            logger.debug('Ignoring unsupported message type: %s', payload.get('type') if isinstance(payload, dict) else type(payload))

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
