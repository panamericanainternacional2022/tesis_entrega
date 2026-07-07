from django.urls import path
from .views import (
    notifications_view,
    toggle_alerts_session_view,
    clear_notifications_view,
    view_notification_count,
    view_clear_alerts,
    history_pdf_view,
)

urlpatterns = [
    path("notifications/", notifications_view, name="notifications"),
    path(
        "notifications/toggle-alerts/",
        toggle_alerts_session_view,
        name="toggle_alerts_session",
    ),
    path(
        "notifications/clear/",
        clear_notifications_view,
        name="clear_notifications",
    ),
    path("api/notifications/count/", view_notification_count, name="api_notification_count"),
    path("api/clear-alerts/", view_clear_alerts, name="api_clear_alerts"),
    path(
        "historial/pdf/",
        history_pdf_view,
        name="history_pdf",
    ),
]
