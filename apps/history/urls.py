from django.urls import path
from .views import (
    history_view,
    clear_history_view,
    view_unread_count,
    view_clear_history,
    history_pdf_view,
)

urlpatterns = [
    path("history/", history_view, name="history"),
    path(
        "history/clear/",
        clear_history_view,
        name="clear_history",
    ),
    path("history/api/count/", view_unread_count, name="api_unread_count"),
    path("history/api/clear-history/", view_clear_history, name="api_clear_history"),
    path(
        "history/pdf/",
        history_pdf_view,
        name="history_pdf",
    ),
]
