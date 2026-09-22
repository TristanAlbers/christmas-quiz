from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import SimpleTestCase
from django.urls import reverse


class ScaffoldTests(SimpleTestCase):
    def test_health_is_public_and_contains_no_game_state(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_index_loads_local_static_assets(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, staticfiles_storage.url("quiz/app.css"))
        self.assertContains(
            response, staticfiles_storage.url("quiz/vendor/htmx.min.js")
        )
