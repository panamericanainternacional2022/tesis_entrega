from django.db import models


class History(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_historial")
    user = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario", blank=True, null=True
    )
    monitoring_equipment = models.ForeignKey(
        "buildings.MonitoringEquipment", on_delete=models.CASCADE, db_column="id_equipo_monitoreo",
        blank=True, null=True,
    )
    date = models.DateTimeField(db_column="fecha", db_index=True)
    message = models.JSONField(default=dict, blank=True, db_column="mensaje")
    resolved = models.BooleanField(default=False, db_column="resuelto")
    fault_type = models.CharField(max_length=50, null=True, blank=True, db_column="tipo_falla")
    affected_variables = models.JSONField(default=list, blank=True, db_column="variables_afectadas")

    class Meta:
        db_table = "historial"

    def __str__(self) -> str:
        msg_str = str(self.message)
        return f"[{self.date}] {msg_str[:60]}"


class UserDismissedHistory(models.Model):
    user = models.ForeignKey(
        "users.Usuario", on_delete=models.CASCADE, db_column="id_usuario"
    )
    history_record = models.ForeignKey(
        History, on_delete=models.CASCADE, db_column="id_historial"
    )
    dismissed_at = models.DateTimeField(auto_now_add=True, db_column="descartado_en")

    class Meta:
        db_table = "historial_descartado"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "history_record"],
                name="uq_user_history_dismissed",
            )
        ]

    def __str__(self) -> str:
        return f"User {self.user_id} dismissed history #{self.history_record_id}"
