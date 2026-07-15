from django.urls import path
from .views import (
    history_view,
    clear_history_view,
    view_unread_count,
    sse_unread_count_stream,
    history_pdf_view,
    resolve_alert_view,
)

urlpatterns = [
    path("history/", history_view, name="history"),
    path(
        "history/clear/",
        clear_history_view,
        name="clear_history",
    ),
    path("history/api/count/", view_unread_count, name="api_unread_count"),
    path("history/api/sse/count/", sse_unread_count_stream, name="api_sse_unread_count"),
    path("history/<int:record_id>/resolve/", resolve_alert_view, name="resolve_alert"),
    path(
        "history/pdf/",
        history_pdf_view,
        name="history_pdf",
    ),
]
