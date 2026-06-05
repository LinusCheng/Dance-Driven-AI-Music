from typing import Dict

NUMERIC_FIELDS = ('energy', 'openness', 'rotation', 'smile', 'mouthOpen')


class ExponentialSmoother:
    def __init__(self, alpha: float = 0.32) -> None:
        self.alpha = alpha
        self._state: Dict[str, float] = {}

    def smooth(self, key: str, value: float) -> float:
        previous = self._state.get(key)
        if previous is None:
            smoothed = value
        else:
            smoothed = previous * (1 - self.alpha) + value * self.alpha

        self._state[key] = smoothed
        return smoothed

    def smooth_state(self, dance_state: Dict[str, float]) -> Dict[str, float]:
        result = dict(dance_state)
        for key in NUMERIC_FIELDS:
            if key in dance_state:
                result[key] = self.smooth(key, float(dance_state[key]))
        return result
