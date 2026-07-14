from django.urls import path
from .views import daily_summary

urlpatterns = [
    path("api/sensors/daily/<int:building_id>/", daily_summary, name="daily_summary"),
]
