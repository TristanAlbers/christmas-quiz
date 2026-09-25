from dataclasses import dataclass
from typing import Literal

from quiz.domain.phase3 import reconcile_freeze
from quiz.models import AuditEvent, Run, TeamRun
from quiz.persistence import read_snapshot


@dataclass(frozen=True)
class TeamPresentationEvent:
    id: int
    kind: Literal["freeze_attack"]
    attacker_team_id: str
    target_team_id: str
    frozen_team_id: str
    reversed: bool


@dataclass(frozen=True)
class TeamPresentationState:
    opponent_freeze_active: bool = False
    event: TeamPresentationEvent | None = None


def _latest_freeze_attack(run: Run) -> TeamPresentationEvent | None:
    event = (
        AuditEvent.objects.filter(run=run, action="freeze_attack")
        .order_by("-id")
        .only("id", "team_id", "changes")
        .first()
    )
    if event is None or event.team_id not in {"a", "b"}:
        return None
    changes = event.changes or {}
    target_team_id = changes.get("target_team")
    frozen_team_id = changes.get("frozen_team")
    reversed_attack = changes.get("reversed")
    if (
        target_team_id not in {"a", "b"}
        or frozen_team_id not in {"a", "b"}
        or type(reversed_attack) is not bool
    ):
        return None
    return TeamPresentationEvent(
        id=event.id,
        kind="freeze_attack",
        attacker_team_id=event.team_id,
        target_team_id=target_team_id,
        frozen_team_id=frozen_team_id,
        reversed=reversed_attack,
    )


def get_team_presentation_state(
    run_id: str | None,
    team_id: str,
    gameplay_elapsed_ms: int,
) -> TeamPresentationState:
    if run_id is None or team_id not in {"a", "b"}:
        return TeamPresentationState()
    opponent_id = "b" if team_id == "a" else "a"
    with read_snapshot():
        run = Run.objects.filter(pk=run_id, active=True).first()
        if run is None:
            return TeamPresentationState()
        opponent = TeamRun.objects.get(run=run, team_id=opponent_id)
        effective = reconcile_freeze(
            opponent.activity_state,
            opponent.freeze_started_gameplay_ms,
            gameplay_elapsed_ms,
        )
        return TeamPresentationState(
            opponent_freeze_active=effective.activity_state == "FREEZE",
            event=_latest_freeze_attack(run),
        )
