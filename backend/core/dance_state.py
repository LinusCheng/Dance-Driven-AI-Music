import math
import time
from typing import Any, Dict

VALID_HEIGHTS = {'LOW', 'MID', 'HIGH'}

NumericFields = ('energy', 'openness', 'rotation', 'smile', 'mouthOpen')


def _ensure_number(value: Any, name: str) -> float:
    if value is None:
        raise ValueError(f'Missing numeric field: {name}')

    if isinstance(value, bool):
        raise ValueError(f'Invalid numeric field: {name}')

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid numeric field: {name}')

    if math.isnan(number) or math.isinf(number):
        raise ValueError(f'Numeric field is not finite: {name}')

    return number


def _normalize_height(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        normalized = value.strip().upper()
        if normalized in VALID_HEIGHTS:
            return normalized
    return 'LOW'


def _normalize_gesture(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return 'none'


def _normalize_timestamp(value: Any) -> int:
    if isinstance(value, (int, float)) and not math.isnan(value):
        return int(value)
    return int(time.time() * 1000)


def validate_and_normalize(dance_payload: Any) -> Dict[str, Any]:
    if not isinstance(dance_payload, dict):
        raise ValueError('Dance state must be a JSON object.')

    normalized: Dict[str, Any] = {}

    for field in NumericFields:
        normalized[field] = _ensure_number(dance_payload.get(field), field)

    normalized['leftArmHeight'] = _normalize_height(dance_payload.get('leftArmHeight'))
    normalized['rightArmHeight'] = _normalize_height(dance_payload.get('rightArmHeight'))
    normalized['gestureLeft'] = _normalize_gesture(dance_payload.get('gestureLeft'))
    normalized['gestureRight'] = _normalize_gesture(dance_payload.get('gestureRight'))
    normalized['timestamp'] = _normalize_timestamp(dance_payload.get('timestamp'))

    return normalized
