def apply_pump_recovery(sim) -> None:
    sim._pump_start_grace_ticks = 5


def apply_elevator_recovery(sim) -> None:
    from apps.sensors.simulation.physics.elevator import _clear_elevator_fault_params
    _clear_elevator_fault_params(sim)
    sim._elev_state = "IDLE"
