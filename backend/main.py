import asyncio
import json
import logging
from typing import Any

import websockets

from dance_state import validate_and_normalize
from magenta_controller import MagentaController
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
magenta = MagentaController()


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
            magenta.update_music_state(music_state)

    except websockets.ConnectionClosedOK:
        logger.info('Frontend disconnected cleanly: %s', client_address)
    except websockets.ConnectionClosedError as error:
        logger.info('Frontend disconnected with error: %s', error)
    except Exception as error:
        logger.exception('Connection handler failed: %s', error)
    finally:
        logger.info('Frontend disconnected: %s', client_address)


async def main() -> None:
    magenta.connect()

    async with websockets.serve(handle_connection, '127.0.0.1', 8765):
        logger.info('WebSocket server listening on ws://localhost:8765')
        await asyncio.Future()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Shutting down backend server.')
        magenta.shutdown()
