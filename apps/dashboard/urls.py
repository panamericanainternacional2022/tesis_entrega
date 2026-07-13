from django.urls import path
from django.views.generic import RedirectView

from .views import monitoring_view
from .simulation.streaming import sse_stream
from .simulation.api import api_status
from .simulation.controls import (
    sim_status,
    sim_pause,
    sim_reset,
    sim_inject_fault,
    sim_clear_fault,
    sim_set_speed,
    sim_toggle_pump,
    sim_toggle_elevator,
)

urlpatterns = [
    path("", RedirectView.as_view(url="/login/", permanent=False), name="home"),
    path("monitor/", monitoring_view, name="monitor"),
    path("sse/<int:building_id>/", sse_stream, name="sse_stream"),
    path("api/status/", api_status, name="api_status"),
    path(
        "api/sim/<int:building_id>/status/",
        sim_status,
        name="api_sim_status",
    ),
    path(
        "api/sim/<int:building_id>/pause/",
        sim_pause,
        name="api_sim_pause",
    ),
    path(
        "api/sim/<int:building_id>/reset/",
        sim_reset,
        name="api_sim_reset",
    ),
    path(
        "api/sim/<int:building_id>/inject-fault/",
        sim_inject_fault,
        name="api_sim_inject_fault",
    ),
    path(
        "api/sim/<int:building_id>/clear-fault/",
        sim_clear_fault,
        name="api_sim_clear_fault",
    ),
    path(
        "api/sim/<int:building_id>/set-speed/",
        sim_set_speed,
        name="api_sim_set_speed",
    ),
    path(
        "api/sim/<int:building_id>/toggle-pump/",
        sim_toggle_pump,
        name="api_sim_toggle_pump",
    ),
    path(
        "api/sim/<int:building_id>/toggle-elevator/",
        sim_toggle_elevator,
        name="api_sim_toggle_elevator",
    ),
]
