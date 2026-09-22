from django.apps import AppConfig


class QuizConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "quiz"

    def ready(self):
        # Register the connection-created SQLite policy before the first DB use.
        from quiz import persistence  # noqa: F401
