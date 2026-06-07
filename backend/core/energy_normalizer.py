import math
from typing import Optional


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class EnergyNormalizer:
    def __init__(self, alpha: float = 0.08) -> None:
        self.alpha = alpha
        self.mean: Optional[float] = None
        self.variance = 1.0
        self.smoothed_value = 0.0

    def normalize(self, raw_energy: float) -> float:
        raw = float(raw_energy)

        if self.mean is None:
            self.mean = raw
            self.variance = max(1.0, raw * 0.25)
            self.smoothed_value = clamp(raw / max(1.0, raw))
            return self.smoothed_value

        assert self.mean is not None
        delta = raw - self.mean
        self.mean += self.alpha * delta
        self.variance = max(1e-4, (1 - self.alpha) * self.variance + self.alpha * delta * delta)

        std = math.sqrt(self.variance)
        lower = max(0.0, self.mean - std * 0.75)
        upper = self.mean + std * 2.2
        normalized = clamp((raw - lower) / max(upper - lower, 1e-4))

        # Keep smoother changes in normalized energy.
        self.smoothed_value = self.smoothed_value * (1 - self.alpha) + normalized * self.alpha
        return clamp(self.smoothed_value)
