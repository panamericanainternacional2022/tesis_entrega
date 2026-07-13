from django.urls import path

from .views import (
    user_list_view,
    user_create_view,
    user_update_view,
    user_delete_view,
    check_cedula_uniqueness_view,
    send_test_email,
    send_all_subscribers,
    user_pdf_view,
)

urlpatterns = [
    path("users/", user_list_view, name="user_list"),
    path(
        "users/create/",
        user_create_view,
        name="user_create",
    ),
    path(
        "users/<int:user_id>/edit/",
        user_update_view,
        name="user_edit",
    ),
    path(
        "users/<int:user_id>/delete/",
        user_delete_view,
        name="user_delete",
    ),
    path("api/check-cedula/", check_cedula_uniqueness_view, name="check_cedula"),
    path(
        "api/send-test-email/",
        send_test_email,
        name="send_test_email",
    ),
    path(
        "api/send-all-subscribers/",
        send_all_subscribers,
        name="send_all_subscribers",
    ),
    path(
        "usuarios/pdf/",
        user_pdf_view,
        name="user_pdf",
    ),
]
