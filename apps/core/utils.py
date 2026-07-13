from django.contrib.auth.hashers import check_password

from apps.users.models import Usuario


def verify_password(raw_password: str, user: Usuario) -> bool:
    return check_password(raw_password, user.password)
