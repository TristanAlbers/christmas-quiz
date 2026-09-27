"""Django settings used only by automated tests."""

from .settings import *  # noqa: F403

# Password hashing is deliberately cheap in tests. Runtime configuration continues
# to use Django's production hashers from config.settings.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
