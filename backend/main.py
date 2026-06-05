import argparse
import asyncio
import json
import logging
import sys
from typing import Any, Optional

import websockets

from dance_state import validate_and_normalize
from music_engines.magenta_engine import MagentaEngine
from music_mapper import dance_to_music_state
from smoothing import ExponentialSmoother

logging.basicConfig(
    level=logging.INFO,
    format='[backend] %(asctime)s %(levelname)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('backend')

latest_dance_state: dict[str, Any] = {}
latest_music_state: dict[str, Any] = {}

smoother = ExponentialSmoother(alpha=0.32)
magenta_engine: Optional[MagentaEngine] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backend WebSocket bridge for danceState and Magenta RT2.')
    parser.add_argument('--mock-magenta', action='store_true', help='Force mock Magenta mode.')
    parser.add_argument('--test-magenta', action='store_true', help='Run a short Magenta test and exit.')
    parser.add_argument('--engine', default='mrt2', help='Music engine: "mrt2" (realtime, default) or "batch" (WAV files).')
    return parser.parse_args()


async def handle_connection(websocket: websockets.WebSocketServerProtocol) -> None:
    client_address = websocket.remote_address
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

            try:
                dance_state = validate_and_normalize(payload)
            except ValueError as error:
                logger.warning('Invalid dance state payload: %s', error)
                continue

            smoothed = smoother.smooth_state(dance_state)
            music_state = dance_to_music_state(smoothed)

            latest_dance_state.update(smoothed)
            latest_music_state.update(music_state)

            logger.info('danceState %s', smoothed)
            logger.info('musicState %s', music_state)
            if magenta_engine is not None:
                magenta_engine.update_music_state(music_state)

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
    global magenta_engine
    args = parse_args()

    # select engine implementation
    engine_name = args.engine
    if engine_name == 'mrt2':
        try:
            from music_engines.mrt2_realtime_engine import MRT2RealtimeEngine
            magenta_engine = MRT2RealtimeEngine()
            magenta_engine.connect()
            magenta_engine.start_stream()
            logger.info('Backend: realtime MRT2 audio streaming enabled')
        except Exception as e:
            logger.exception('Failed to start MRT2RealtimeEngine: %s', e)
            logger.info('Falling back to batch mode (WAV generation)')
            magenta_engine = MagentaEngine(use_mock=args.mock_magenta)
    else:
        # 'batch' mode or any other option
        magenta_engine = MagentaEngine(use_mock=args.mock_magenta)
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
        logger.info('Shutting down backend server.')
        if magenta_engine is not None:
            magenta_engine.shutdown()
        return 0
    except Exception as error:
        logger.exception('Backend failed: %s', error)
        if magenta_engine is not None:
            magenta_engine.shutdown()
        return 1


if __name__ == '__main__':
    sys.exit(main())
