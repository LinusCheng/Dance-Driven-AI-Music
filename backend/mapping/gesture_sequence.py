import logging
import time
from collections import deque
from typing import Any, Deque, Dict, Optional


logger = logging.getLogger('Backend.gesture_sequence')

GENRE_NEXT_PAIR = frozenset(('point',))
BPM_UP_PAIR = frozenset(('openPalm', 'point'))
BPM_DOWN_PAIR = frozenset(('openPalm', 'fist'))

GENRE_PRESETS: list[dict[str, str]] = [
    {
        'genre': 'house',
        'prompt': 'bright house groove with open chords and a clean dance pulse',
    },
    {
        'genre': 'disco_funk',
        'prompt': 'playful disco funk with bright rhythm guitar feel and bouncy drums',
    },
    {
        'genre': 'techno',
        'prompt': 'driving techno groove with hard accents and focused low-end momentum',
    },
    {
        'genre': 'ambient',
        'prompt': 'ambient minimal texture with soft motion and sparse delicate rhythm',
    },
    {
        'genre': 'cinematic',
        'prompt': 'cinematic electronic pulse with wide evolving harmony and dramatic lift',
    },
    {
        'genre': 'garage',
        'prompt': 'shuffling UK garage rhythm with syncopated drums and warm chords',
    },
    {
        'genre': 'drum_and_bass',
        'prompt': 'fast drum and bass breakbeat with energetic bass movement',
    },
    {
        'genre': 'trap',
        'prompt': 'dark trap beat with crisp hats, heavy accents, and sparse melody',
    },
    {
        'genre': 'lofi',
        'prompt': 'lofi groove with dusty drums, mellow chords, and relaxed swing',
    },
    {
        'genre': 'afro_house',
        'prompt': 'afro house rhythm with rolling percussion and warm hypnotic harmony',
    },
]


class GestureSequenceDetector:
    def __init__(
        self,
        window_seconds: float = 5.0,
        debounce_seconds: float = 0.35,
        genre_cooldown_seconds: float = 8.0,
        bpm_cooldown_seconds: float = 2.0,
    ) -> None:
        self.window_seconds = window_seconds
        self.debounce_seconds = debounce_seconds
        self.genre_cooldown_seconds = genre_cooldown_seconds
        self.bpm_cooldown_seconds = bpm_cooldown_seconds
        self.events: Deque[dict[str, Any]] = deque()
        self.genre_index = 0
        self.current_genre = GENRE_PRESETS[self.genre_index]['genre']
        self.current_genre_prompt = GENRE_PRESETS[self.genre_index]['prompt']
        self.bpm = 120
        self.last_genre_change_ts = 0.0
        self.last_bpm_change_ts = 0.0
        self._last_genre_cooldown_log_ts = 0.0
        self._candidate_gesture: Optional[str] = None
        self._candidate_started_ts = 0.0
        self._last_accepted_gesture: Optional[str] = None

    def update(self, dance_state: dict[str, Any]) -> dict[str, Any]:
        now = time.monotonic()
        gesture = self._dominant_gesture(dance_state)
        accepted_event = self._accept_stable_gesture(gesture, now)

        if accepted_event is not None:
            self.events.append(accepted_event)
            logger.info(
                'Gesture accepted: %s recent=%s',
                accepted_event['gesture'],
                ' -> '.join(event['gesture'] for event in self.events),
            )

        self._trim(now)
        matched = self._detect_two_hand_genre_pair(dance_state, now)
        if matched is None:
            matched = self._detect_bpm_pair(dance_state, now)

        return {
            'genre': self.current_genre,
            'genrePrompt': self.current_genre_prompt,
            'bpm': self.bpm,
            'bpmPrompt': f'at around {self.bpm} BPM',
            'lastSequence': matched,
            'recentGestures': [event['gesture'] for event in self.events],
        }

    def _dominant_gesture(self, dance_state: dict[str, Any]) -> str:
        right = str(dance_state.get('gestureRight') or 'none')
        left = str(dance_state.get('gestureLeft') or 'none')

        if right != 'none':
            return right
        if left != 'none':
            return left
        return 'none'

    def _accept_stable_gesture(self, gesture: str, now: float) -> Optional[dict[str, Any]]:
        if gesture == 'none':
            self._candidate_gesture = None
            self._candidate_started_ts = 0.0
            self._last_accepted_gesture = None
            return None

        if gesture != self._candidate_gesture:
            self._candidate_gesture = gesture
            self._candidate_started_ts = now
            return None

        if now - self._candidate_started_ts < self.debounce_seconds:
            return None

        if gesture == self._last_accepted_gesture:
            return None

        self._last_accepted_gesture = gesture
        return {'gesture': gesture, 'timestamp': now}

    def _trim(self, now: float) -> None:
        while self.events and now - float(self.events[0]['timestamp']) > self.window_seconds:
            self.events.popleft()

    def _detect_two_hand_genre_pair(self, dance_state: dict[str, Any], now: float) -> Optional[dict[str, Any]]:
        left = str(dance_state.get('gestureLeft') or 'none')
        right = str(dance_state.get('gestureRight') or 'none')

        if left == 'none' or right == 'none' or left != right:
            return None

        pair = frozenset((left, right))
        if pair == GENRE_NEXT_PAIR:
            return self._change_genre(now, {'gesturePair': [left, right], 'source': 'two_hand_pair'})

        return None

    def _detect_bpm_pair(self, dance_state: dict[str, Any], now: float) -> Optional[dict[str, Any]]:
        left = str(dance_state.get('gestureLeft') or 'none')
        right = str(dance_state.get('gestureRight') or 'none')

        if left == 'none' or right == 'none' or left == right:
            return None

        pair = frozenset((left, right))
        if pair == BPM_UP_PAIR:
            return self._change_bpm(now, pair, 5)
        if pair == BPM_DOWN_PAIR:
            return self._change_bpm(now, pair, -5)

        return None

    def _change_bpm(self, now: float, gesture_pair: frozenset[str], amount: int) -> Optional[dict[str, Any]]:
        if now - self.last_bpm_change_ts < self.bpm_cooldown_seconds:
            return None

        self.bpm = max(70, min(170, self.bpm + amount))
        self.last_bpm_change_ts = now
        logger.info('BPM gesture matched: pair=%s bpm=%s amount=%+d', sorted(gesture_pair), self.bpm, amount)
        return {
            'name': 'bpm_change',
            'gesturePair': sorted(gesture_pair),
            'bpm': self.bpm,
            'amount': amount,
        }

    def _change_genre(self, now: float, details: dict[str, Any]) -> Optional[dict[str, Any]]:
        seconds_since_change = now - self.last_genre_change_ts
        if seconds_since_change < self.genre_cooldown_seconds:
            if now - self._last_genre_cooldown_log_ts >= 1.0:
                logger.info(
                    'Genre gesture matched but cooling down: source=%s wait=%.1fs',
                    details.get('source', 'unknown'),
                    self.genre_cooldown_seconds - seconds_since_change,
                )
                self._last_genre_cooldown_log_ts = now
            return None

        self.genre_index = (self.genre_index + 1) % len(GENRE_PRESETS)
        preset = GENRE_PRESETS[self.genre_index]
        self.current_genre = preset['genre']
        self.current_genre_prompt = preset['prompt']
        self.last_genre_change_ts = now

        logger.info(
            'Genre gesture matched: source=%s genre=%s prompt=%s',
            details.get('source', 'unknown'),
            self.current_genre,
            self.current_genre_prompt,
        )

        return {
            'name': 'genre_next',
            **details,
            'genre': self.current_genre,
            'prompt': self.current_genre_prompt,
        }
