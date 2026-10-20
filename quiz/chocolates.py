import json
from pathlib import Path

_CHOCOLATES = json.loads(
    (Path(__file__).resolve().parent / "chocolate_manifest.json").read_text()
)
for _subject, _asset in _CHOCOLATES["assets"].items():
    left, top, right, bottom = _asset["visible_bounds_alpha_gt_16"]
    # Match the handoff viewport: trim transparent margins with 12px breathing room.
    _asset["view_box"] = (
        f"{left - 12} {top - 12} {right - left + 24} {bottom - top + 24}"
    )
    _asset["static_path"] = "quiz/chocolates/" + Path(_asset["file"]).name
    _asset["is_broad"] = _subject in {"iglo", "trein"}
    _asset["label"] = "dennenboom" if _subject == "denneboom" else _subject


def get_door_chocolate(number):
    """Return an approved door's subject and enriched artwork metadata."""
    entry = _CHOCOLATES["mapping"][number - 1]
    return entry["subject"], _CHOCOLATES["assets"][entry["subject"]]
