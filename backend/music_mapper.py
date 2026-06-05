from typing import Dict, List


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _gesture_event(left_gesture: str, right_gesture: str) -> str:
    if right_gesture and right_gesture.lower() != 'none':
        return f'right_{right_gesture}'
    if left_gesture and left_gesture.lower() != 'none':
        return f'left_{left_gesture}'
    return 'none'


def _prompt_hints(dance_state: Dict[str, float]) -> List[str]:
    hints: List[str] = []
    energy = dance_state.get('energy', 0.0)
    openness = dance_state.get('openness', 0.0)
    smile = dance_state.get('smile', 0.0)
    mouth_open = dance_state.get('mouthOpen', 0.0)

    if energy > 0.65:
        hints.append('energetic rhythm')
    else:
        hints.append('steady groove')

    if openness > 0.5:
        hints.append('bright open harmony')
    else:
        hints.append('closed textured harmony')

    if mouth_open > 0.4:
        hints.append('accented expression')

    if smile > 0.6 and 'bright open harmony' not in hints:
        hints.append('warm melodic flow')

    return hints


def dance_to_music_state(dance_state: Dict[str, float]) -> Dict[str, object]:
    energy = _clamp(dance_state.get('energy', 0.0))
    openness = _clamp(dance_state.get('openness', 0.0))
    rotation = dance_state.get('rotation', 0.0)
    smile = _clamp(dance_state.get('smile', 0.0))
    mouth_open = _clamp(dance_state.get('mouthOpen', 0.0))

    brightness = _clamp(openness + smile * 0.14)
    tension = _clamp(abs(rotation) * 0.6 + max(0.0, 0.15 - openness * 0.15))

    return {
        'density': energy,
        'brightness': brightness,
        'tension': tension,
        'rhythmicActivity': energy,
        'harmonyWidth': openness,
        'gestureEvent': _gesture_event(dance_state.get('gestureLeft', ''), dance_state.get('gestureRight', '')),
        'promptHints': _prompt_hints(dance_state),
    }
