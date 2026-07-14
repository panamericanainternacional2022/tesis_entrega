from django.db import models
from django.utils import timezone


class SensorReading(models.Model):
    building = models.ForeignKey(
        "buildings.Building", on_delete=models.CASCADE,
        db_column="id_edificio", related_name="sensor_readings",
    )
    variable = models.CharField(max_length=50, db_column="variable")
    value = models.FloatField(db_column="valor")
    risk = models.CharField(max_length=20, db_column="riesgo")
    timestamp = models.DateTimeField(default=timezone.now, db_column="fecha", db_index=True)

    class Meta:
        db_table = "lectura_sensor"
        indexes = [
            models.Index(fields=["building", "variable", "timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.variable} = {self.value} ({self.risk}) @ {self.timestamp}"
