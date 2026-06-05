from typing import Dict, List

from energy_normalizer import EnergyNormalizer


energy_normalizer = EnergyNormalizer()


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _gesture_event(left_gesture: str, right_gesture: str) -> str:
    if right_gesture and right_gesture.lower() != 'none':
        return f'right_{right_gesture}'
    if left_gesture and left_gesture.lower() != 'none':
        return f'left_{left_gesture}'
    return 'none'


def _prompt_hints(state: Dict[str, float]) -> List[str]:
    hints: List[str] = []
    energy = state.get('normalizedEnergy', state.get('energy', 0.0))
    openness = state.get('openness', 0.0)
    smile = state.get('smile', 0.0)
    mouth_open = state.get('mouthOpen', 0.0)

    if energy > 0.65:
        hints.append('energetic rhythm')
    elif energy > 0.3:
        hints.append('moving rhythm')
    else:
        hints.append('ambient sparse texture')

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
    raw_energy = float(dance_state.get('energy', 0.0))
    normalized_energy = energy_normalizer.normalize(raw_energy)
    openness = _clamp(dance_state.get('openness', 0.0))
    rotation = dance_state.get('rotation', 0.0)
    smile = _clamp(dance_state.get('smile', 0.0))
    mouth_open = _clamp(dance_state.get('mouthOpen', 0.0))

    brightness = _clamp(openness + smile * 0.14)
    tension = _clamp(abs(rotation) * 0.6 + max(0.0, 0.15 - openness * 0.15))

    music_state = {
        'rawEnergy': raw_energy,
        'normalizedEnergy': normalized_energy,
        'density': normalized_energy,
        'brightness': brightness,
        'tension': tension,
        'rhythmicActivity': normalized_energy,
        'harmonyWidth': openness,
        'gestureEvent': _gesture_event(dance_state.get('gestureLeft', ''), dance_state.get('gestureRight', '')),
        'promptHints': _prompt_hints({
            'normalizedEnergy': normalized_energy,
            'openness': openness,
            'smile': smile,
            'mouthOpen': mouth_open,
        }),
    }

    return music_state
