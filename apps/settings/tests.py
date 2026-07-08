from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.hashers import make_password
from apps.users.models import Persona, Usuario


class ConfigurationViewTests(TestCase):
    def setUp(self) -> None:
        self.persona = Persona.objects.create(ci="12345678", first_name="Admin", first_last_name="User", email="a@a.com")
        self.usuario = Usuario.objects.create(
            username="admin", password=make_password("admin123"), id_persona=self.persona, rol="SA", registered=True,
        )
        self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})

    def test_get_config_page(self) -> None:
        response = self.client.get(reverse("configuration"))
        self.assertEqual(response.status_code, 200)

    def test_update_email(self) -> None:
        response = self.client.post(reverse("configuration"), {
            "action": "update_profile",
            "email": "nuevo@test.com",
            "username": "",
            "current_password": "admin123",
            "new_password": "",
            "confirm_password": "",
        })
        self.assertEqual(response.status_code, 302)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.email, "nuevo@test.com")

    def test_wrong_current_password(self) -> None:
        response = self.client.post(reverse("configuration"), {
            "action": "change_password",
            "email": "",
            "username": "",
            "current_password": "wrong",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no es correcta")
