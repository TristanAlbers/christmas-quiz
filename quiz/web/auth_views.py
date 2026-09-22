"""Session login endpoints; role checks use the persisted account mapping."""

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from quiz.auth import actor_for_user
from quiz.contracts import ApplicationError
from quiz.web.auth_forms import AdminLoginForm, TeamLoginForm


def _login(request, form_type, intended_role):
    if request.method == "POST":
        form = form_type(request.POST)
        if form.is_valid():
            if intended_role == "team":
                username = f"team-{form.cleaned_data['team']}"
                password = form.cleaned_data["pin"]
            else:
                username = form.cleaned_data["username"]
                password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user is not None:
                try:
                    actor = actor_for_user(user)
                except ApplicationError:
                    actor = None
                if actor is not None and actor.role == intended_role:
                    login(request, user)
                    return redirect("index")
            form.add_error(None, "Invalid credentials")
    else:
        form = form_type()
    return render(request, "quiz/login.html", {"form": form, "role": intended_role})


@never_cache
@csrf_protect
def team_login(request):
    return _login(request, TeamLoginForm, "team")


@never_cache
@csrf_protect
def admin_login(request):
    return _login(request, AdminLoginForm, "admin")


@never_cache
@csrf_protect
def sign_out(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect("index")
