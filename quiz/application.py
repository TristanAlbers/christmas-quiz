"""Stable application facade.

The pre-Phase-6 use cases remain in `_application_core`. Challenge-specific
projection/command behavior is layered in `phase6_application` so the amended
Phase-6 contract can evolve without duplicating or destabilizing unrelated game
flows. Existing `quiz.application` imports remain the supported API.
"""

from . import _application_core as _core
from ._application_core import *  # noqa: F403
from .phase6_application import (  # noqa: F401
    get_admin_state,
    get_public_state,
    get_team_state,
    initiate_challenge,
    submit_challenge_answer,
)


def __getattr__(name):
    """Preserve access to private helpers used by focused legacy tests."""
    return getattr(_core, name)
