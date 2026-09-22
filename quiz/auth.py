"""Resolve actors solely from an authenticated Django user and stored role."""

from quiz.contracts import Actor, ApplicationError
from quiz.models import AccountRole


def actor_for_user(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        raise ApplicationError("unauthenticated")
    try:
        role = AccountRole.objects.get(user_id=user.pk)
    except AccountRole.DoesNotExist as exc:
        raise ApplicationError("forbidden") from exc
    if role.role == "team" and role.team_id in ("a", "b"):
        return Actor(user_id=user.pk, role="team", team_id=role.team_id)
    if role.role == "admin" and role.team_id is None:
        return Actor(user_id=user.pk, role="admin")
    raise ApplicationError("forbidden")
