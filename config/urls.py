from django.urls import include, path

urlpatterns = [path("", include("quiz.web.urls"))]
