import time

from apps.sensors.simulation.models import BuildingSimulator


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def is_locked(sim: BuildingSimulator, var: str) -> bool:
    if hasattr(sim, "manual_overrides") and isinstance(sim.manual_overrides, dict):
        return time.time() < sim.manual_overrides.get(var, 0)
    return False
