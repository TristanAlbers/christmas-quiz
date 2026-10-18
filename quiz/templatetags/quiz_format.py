import json
from pathlib import Path

from django import template

register = template.Library()


STATE_LABELS = {
    "READY": "Klaar om te starten",
    "ADVENT_QUIZ": "Adventquiz",
    "MUSIC_QUIZ": "Muziek Quiz",
    "PAUSED": "Gepauzeerd",
    "FINISHED": "Afgerond",
    "PUZZLE": "Puzzel",
    "FREEZE": "Bevroren",
}

CHALLENGE_LABELS = {
    "starting": "Voorbereiden",
    "active": "Bezig",
    "resolved": "Afgerond",
}

FEEDBACK_LABELS = {
    "Correct answer. Puzzle completed.": "Goed antwoord. Puzzel afgerond.",
    "Incorrect answer. Try again.": "Onjuist antwoord. Probeer het opnieuw.",
    "Correct. Your team won this Music question.": (
        "Goed! Jullie team wint deze muziekvraag."
    ),
    "Incorrect. Keep trying.": "Onjuist. Probeer het opnieuw.",
    "Challenge won. The result is final.": (
        "Uitdaging gewonnen. De uitslag staat vast."
    ),
    "Incorrect Challenge answer. Keep trying.": (
        "Onjuist antwoord op de uitdaging. Probeer het opnieuw."
    ),
    "Hint was already revealed. No token used.": (
        "De hint was al zichtbaar. Er is geen hint gebruikt."
    ),
    "Hint token purchased.": "Hint gekocht.",
    "Hint revealed.": "Hint onthuld.",
    "Puzzle skipped and completed.": "Vraag overgeslagen en afgerond.",
    "The opposing team's Reverse redirected the Freeze to you.": (
        "De Uno Reverse van het andere team kaatste de Freeze naar jullie terug."
    ),
    "The opposing team is frozen.": "Het andere team is bevroren.",
    "Uno Reverse purchased and armed.": "Uno Reverse gekocht en geactiveerd.",
    "Challenge starting. Gather around!": "De uitdaging begint. Verzamel je team!",
}


@register.filter
def elapsed_hhmmss(value):
    """Format authoritative elapsed milliseconds as fixed HH:MM:SS."""
    try:
        total_seconds = max(0, int(value) // 1000)
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@register.filter
def remaining_mmss(value):
    """Display the server-projected remaining duration, rounded up to a second."""
    try:
        seconds = max(0, (int(value) + 999) // 1000)
    except (TypeError, ValueError):
        seconds = 0
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


@register.filter
def state_label(value):
    """Map internal state identifiers to Dutch presentation labels."""
    return STATE_LABELS.get(str(value), str(value).replace("_", " ").title())


@register.filter
def challenge_label(value):
    """Map Challenge presentation states without exposing technical identifiers."""
    return CHALLENGE_LABELS.get(str(value), str(value).replace("_", " ").title())


@register.filter
def dutch_feedback(value):
    """Translate application feedback at the presentation boundary."""
    return FEEDBACK_LABELS.get(str(value), str(value))


# Fixed approved clue artwork, independent of team and game configuration.
_CHOCOLATES = json.loads(
    (Path(__file__).resolve().parent.parent / "chocolate_manifest.json").read_text()
)
for _asset in _CHOCOLATES["assets"].values():
    left, top, right, bottom = _asset["visible_bounds_alpha_gt_16"]
    # Match the handoff viewport: trim transparent margins with 12px breathing room.
    _asset["view_box"] = (
        f"{left - 12} {top - 12} {right - left + 24} {bottom - top + 24}"
    )
    _asset["static_path"] = "quiz/chocolates/" + Path(_asset["file"]).name


@register.filter
def door_chocolate(number):
    """Look up an earned door's approved artwork; never infer a cycling motif."""
    entry = _CHOCOLATES["mapping"][number - 1]
    return _CHOCOLATES["assets"][entry["subject"]]
