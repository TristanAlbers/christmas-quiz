from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class AdventCalendarPresentationTests(SimpleTestCase):
    def test_calendar_uses_doors_and_chocolates_without_visible_status_badges(self):
        progress = {
            "completed_count": 1,
            "is_finished": False,
            "doors": [
                {"number": 1, "status": "completed"},
                {"number": 2, "status": "current"},
                {"number": 3, "status": "future"},
            ],
        }

        html = render_to_string(
            "quiz/_advent_calendar.html",
            {"progress": progress, "team_id": "a"},
        )

        self.assertEqual(html.count("advent-door__chocolate"), 3)
        self.assertIn("advent-door--completed", html)
        self.assertIn("advent-door--current", html)
        self.assertIn("advent-door--future", html)
        self.assertNotIn("advent-door__status", html)
        self.assertNotIn(">Current<", html)
        self.assertNotIn(">Locked<", html)
        self.assertNotIn("✓", html)

    def test_completed_door_has_a_persistent_open_visual_state(self):
        stylesheet_path = finders.find("quiz/advent-calendar.css")
        self.assertIsNotNone(stylesheet_path)
        stylesheet = Path(stylesheet_path).read_text(encoding="utf-8")

        self.assertIn(".advent-door--completed .advent-door__flap", stylesheet)
        self.assertIn("transform: rotateY(-112deg);", stylesheet)
        self.assertIn(".advent-door__chocolate", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
