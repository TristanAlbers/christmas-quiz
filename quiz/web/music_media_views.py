"""Serve only the active run's currently shareable Music audio."""

from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache

from quiz.configuration import snapshot_music_audio_path
from quiz.models import MusicQuiz, Run
from quiz.persistence import read_snapshot


@never_cache
def current_music_audio(request, run_id):
    """Public TV audio boundary; the URL never addresses a future question."""
    with read_snapshot():
        try:
            run = Run.objects.get(
                pk=run_id,
                active=True,
                global_state="MUSIC_QUIZ",
            )
            music = MusicQuiz.objects.get(
                run=run,
                phase="question",
                current_question_number__isnull=False,
            )
            path = snapshot_music_audio_path(run, music.current_question_number)
            if path is None:
                raise Http404
            file = path.open("rb")
        except (Run.DoesNotExist, MusicQuiz.DoesNotExist, OSError) as exc:
            raise Http404 from exc
    response = FileResponse(file)
    response["Cache-Control"] = "public, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
