from django.db import models


class ThresholdConfig(models.Model):
    building = models.ForeignKey(
        "buildings.Building",
        on_delete=models.CASCADE,
        db_column="id_edificio",
        related_name="thresholds",
    )
    variable = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, default="higher")
    high = models.FloatField()
    critic = models.FloatField()
    crit_low = models.FloatField(null=True, blank=True)
    crit_high = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "umbral_config"
        unique_together = (("building", "variable"))
        verbose_name = "Configuración de Umbral"
        verbose_name_plural = "Configuraciones de Umbrales"

    def __str__(self) -> str:
        return f"[Ed.{self.building_id}] {self.variable}: {self.direction} high={self.high} critic={self.critic}"
