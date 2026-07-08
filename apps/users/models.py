from django.db import models


class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True)
    ci = models.CharField(max_length=16, unique=True)
    first_name = models.CharField(max_length=40, db_column="primer_nombre")
    middle_name = models.CharField(max_length=40, db_column="segundo_nombre", blank=True, default="")
    first_last_name = models.CharField(max_length=40, db_column="primer_apellido")
    second_last_name = models.CharField(max_length=40, db_column="segundo_apellido", blank=True, default="")
    email = models.EmailField(max_length=75, unique=True)

    class Meta:
        db_table = "persona"

    def get_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.first_last_name, self.second_last_name]
        return " ".join(p for p in parts if p)

    def __str__(self):
        return self.get_full_name()


class Usuario(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)
    id_persona = models.OneToOneField(
        Persona, on_delete=models.CASCADE, db_column="id_persona"
    )
    rol = models.CharField(
        max_length=2, default="US",
        choices=[("US", "Usuario"), ("SA", "Super Administrador")],
    )
    registered = models.BooleanField(default=False, db_column="registrado")
    class Meta:
        db_table = "usuario"

    def __str__(self):
        return self.username
