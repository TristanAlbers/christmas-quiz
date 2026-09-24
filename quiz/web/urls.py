from django.urls import path

from quiz.web import auth_views, media_views, music_media_views, views

urlpatterns = [
    path("", views.index, name="index"),
    path("health/", views.health, name="health"),
    path("login/", auth_views.team_login, name="login"),
    path("admin-login/", auth_views.admin_login, name="admin_login"),
    path("logout/", auth_views.sign_out, name="logout"),
    path("team/", views.team, name="team"),
    path("team/state/", views.team_state, name="team_state"),
    path("team/answer/", views.team_answer, name="team_answer"),
    path("team/music-answer/", views.team_music_answer, name="team_music_answer"),
    path("team/action/<str:action>/", views.team_action, name="team_action"),
    path("admin-game/", views.admin_game, name="admin_game"),
    path("admin-game/state/", views.admin_state, name="admin_state"),
    path("admin-game/start/", views.admin_start, name="admin_start"),
    path("admin-game/action/<str:action>/", views.admin_action, name="admin_action"),
    path("overview/", views.overview, name="overview"),
    path("overview/state/", views.overview_state, name="overview_state"),
    path(
        "music/audio/<uuid:run_id>/",
        music_media_views.current_music_audio,
        name="current_music_audio",
    ),
    path(
        "media/<uuid:run_id>/<str:team_id>/<path:asset_path>/",
        media_views.private_media,
        name="private_media",
    ),
]
