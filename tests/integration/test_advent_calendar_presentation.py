from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.templatetags.static import static


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

        self.assertEqual(html.count("advent-door__chocolate"), 1)
        self.assertIn(static("quiz/chocolates/engel.png"), html)
        self.assertNotIn(static("quiz/chocolates/muzieknoot.png"), html)
        self.assertNotIn('>1</span>', html)
        self.assertIn('>2</span>', html)
        self.assertIn('>3</span>', html)
        self.assertIn("advent-door--completed", html)
        self.assertIn("advent-door--current", html)
        self.assertIn("advent-door--future", html)
        self.assertNotIn("advent-door__status", html)
        self.assertNotIn(">Current<", html)
        self.assertNotIn(">Locked<", html)
        self.assertNotIn("✓", html)

    def test_team_label_sits_outside_board_and_calendar_title_is_prominent(self):
        progress = {
            "completed_count": 0,
            "is_finished": False,
            "doors": [{"number": 1, "status": "current"}],
        }

        html = render_to_string(
            "quiz/_advent_calendar.html",
            {"progress": progress, "team_id": "b"},
        )

        team_label = html.index('class="advent-team-heading"')
        board = html.index('class="advent-progress__board"')
        title = html.index('class="advent-progress__title"')
        doors = html.index('class="advent-calendar"')
        self.assertLess(team_label, board)
        self.assertLess(title, doors)
        self.assertIn("Team B", html)
        self.assertIn("Adventkalender", html)

    def test_completed_door_has_a_persistent_open_visual_state(self):
        stylesheet_path = finders.find("quiz/advent-calendar.css")
        self.assertIsNotNone(stylesheet_path)
        stylesheet = Path(stylesheet_path).read_text(encoding="utf-8")

        self.assertIn(".advent-door--completed .advent-door__flap", stylesheet)
        self.assertIn("transform: rotateY(-112deg);", stylesheet)
        self.assertIn(".advent-door__chocolate", stylesheet)
        self.assertIn(".advent-progress__title", stylesheet)
        self.assertIn('"Segoe Script"', stylesheet)
        self.assertIn("#c13b45", stylesheet)
        self.assertIn("#267055", stylesheet)
        self.assertIn("#d6a133", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
