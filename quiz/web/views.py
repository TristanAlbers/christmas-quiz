from django.http import JsonResponse
from django.shortcuts import render


def index(request):
    return render(request, "quiz/index.html")


def health(request):
    return JsonResponse({"status": "ok"})
