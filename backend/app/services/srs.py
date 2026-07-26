"""SM-2 spaced repetition, the standard well-understood algorithm (not a
custom scheme) -- used for the vocab deck. quality is 0-5 per the original
SM-2 spec; the frontend only needs to offer two buttons ("Again" -> quality
2, "Good" -> quality 4) to cover the common case."""
from dataclasses import dataclass

MIN_EASE = 1.3
DEFAULT_EASE = 2.5


@dataclass
class SRSState:
    ease: float
    interval_days: int
    reps: int


def sm2_review(state: SRSState, quality: int) -> SRSState:
    """Pure. quality < 3 means "forgot it" -- reset the interval and rep
    streak but keep the ease penalty (matches the textbook SM-2 algorithm)."""
    quality = max(0, min(5, quality))

    if quality < 3:
        return SRSState(ease=_next_ease(state.ease, quality), interval_days=1, reps=0)

    if state.reps == 0:
        interval = 1
    elif state.reps == 1:
        interval = 6
    else:
        interval = round(state.interval_days * state.ease)

    return SRSState(ease=_next_ease(state.ease, quality), interval_days=interval, reps=state.reps + 1)


def _next_ease(ease: float, quality: int) -> float:
    next_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return round(max(MIN_EASE, next_ease), 2)
