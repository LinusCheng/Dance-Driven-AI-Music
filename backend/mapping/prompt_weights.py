from typing import Any, Dict


PROMPT_NODE_NAMES = (
    'node_1',
    'node_2',
    'node_3',
    'node_4',
    'node_5',
    'node_6',
)

PROMPT_NODE_TEXTS = {
    'node_1': 'dynamic music control',
    'node_2': 'bright disco house groove',
    'node_3': 'minimal ambient texture',
    'node_4': 'driving techno industrial pulse',
    'node_5': 'cinematic experimental motion',
    'node_6': 'funky syncopated bass and drums',
}


def _clamp_weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(1.0, number))


def default_prompt_weights() -> Dict[str, float]:
    return {name: 0.0 for name in PROMPT_NODE_NAMES}


def default_prompt_texts() -> Dict[str, str]:
    return dict(PROMPT_NODE_TEXTS)


def normalize_prompt_texts(payload: Any) -> Dict[str, str]:
    texts = default_prompt_texts()
    if not isinstance(payload, dict):
        return texts

    for name in PROMPT_NODE_NAMES:
        if name in payload:
            texts[name] = str(payload[name] or '').strip()[:160]

    return texts


def normalize_prompt_weights(payload: Any) -> Dict[str, float]:
    weights = default_prompt_weights()
    if not isinstance(payload, dict):
        return weights

    for name in PROMPT_NODE_NAMES:
        if name in payload:
            weights[name] = _clamp_weight(payload[name])

    return weights
