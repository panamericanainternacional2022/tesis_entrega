import time
import logging

import eventlet

from apps.sensors.sensor_config import (
    PUMP_VARS, ELEVATOR_VARS, SYSTEM_VARS, ALERT_VARS,
    RISK_CRITICO, RISK_ALTO, RISK_NORMAL, BOOLEAN_VARS, ENUM_VARS,
    ENUM_RISK_VALUES,
    SIM_TICK_INTERVAL,
)
from apps.sensors.simulation.constants import (
    MAX_HISTORY_SIZE,
)
from apps.sensors.simulation.models import BuildingSimulator
from apps.sensors.simulation.globals import simulators
from apps.sensors.simulation.simulation_engine import update_sensor_data


logger = logging.getLogger(__name__)

_MAX_BACKOFF_TICKS: int = 30


def _run_sim_tick(sim: BuildingSimulator) -> None:
    if sim.sim_paused:
        return
    update_sensor_data(active_sim=sim)
    alert_vars = _get_alert_vars(sim)
    risk_cache = _process_sensor_alerts(sim, alert_vars)
    _build_history_records(sim, alert_vars, risk_cache)


def _get_alert_vars(sim: BuildingSimulator) -> set[str]:
    alert_vars = set()
    if "bomba" in sim.equipment_types:
        alert_vars.update(PUMP_VARS)
    if "elevador" in sim.equipment_types:
        alert_vars.update(ELEVATOR_VARS)
    return alert_vars


# Minimum consecutive ticks a sensor must stay in Alto/Crítico before an
# alert is generated.  At sim_speed=1 each tick ≈ 1 second.
# This eliminates single-tick pressure/flow spikes caused by pump start-up
# or minor demand oscillations from creating spurious alerts.
ALERT_DEBOUNCE_TICKS: int = 3


def _process_sensor_alerts(sim: BuildingSimulator, alert_vars: set[str]) -> dict:
    from apps.core.services.risk_service import classify_risk
    from apps.sensors.sensor_config import PUMP_VARS, ELEVATOR_VARS
    from apps.thresholds.services import get_thresholds

    thresholds = get_thresholds(sim.edificio_id)
    risk_cache: dict[str, str] = {}

    # Per-variable consecutive-high-risk tick counter (debounce)
    if not hasattr(sim, "_alert_consecutive"):
        sim._alert_consecutive = {}

    for var, value in sim.sensor_data.items():
        if var not in alert_vars:
            continue

        # Skip alerts while variable is in progressive transition
        if var in getattr(sim, "manual_overrides", {}):
            sim.active_alerts.pop(var, None)
            sim._alert_consecutive.pop(var, None)
            continue

        # Skip alerts during pump startup transient
        if var in {"flow_rate", "pressure"} and getattr(sim, "_pump_start_grace_ticks", 0) > 0:
            sim.active_alerts.pop(var, None)
            sim._alert_consecutive.pop(var, None)
            continue

        if var in BOOLEAN_VARS:
            _handle_motor_stuck_alert(sim, var, value)
            risk_cache[var] = RISK_CRITICO if value else RISK_NORMAL
            continue
        if var in ENUM_VARS:
            _handle_enum_alert(sim, var, value)
            risky_values = ENUM_RISK_VALUES.get(var, set())
            str_val = str(value).lower() if value is not None else ""
            risk_cache[var] = RISK_CRITICO if str_val in risky_values else RISK_NORMAL
            continue
        from apps.events.alerts.engine import send_alert
        from apps.events.services.alert_service import get_professional_action
        risk, _ = classify_risk(
            var, value, thresholds,
            pump_on=sim.pump_on,
            speed=sim.sensor_data.get("speed", 0.0),
            door_close_attempts=sim.door_close_attempts,
            pos_stuck=getattr(sim, "_elev_pos_sensor_stuck", False),
            elevator_on=sim.elevator_on,
        )
        risk_cache[var] = risk
        if risk in (RISK_ALTO, RISK_CRITICO):
            # Increment debounce counter; only fire once threshold is met
            consecutive = sim._alert_consecutive.get(var, 0) + 1
            sim._alert_consecutive[var] = consecutive
            if consecutive >= ALERT_DEBOUNCE_TICKS:
                action = get_professional_action(var, risk, value)
                send_alert(var, value, risk, action, sim=sim)
        else:
            sim.active_alerts.pop(var, None)
            sim._alert_consecutive.pop(var, None)
    from apps.events.alerts.engine import check_rationing
    _skip_rationing = (
        getattr(sim, "_pump_start_grace_ticks", 0) > 0
        or "flow_rate" in getattr(sim, "manual_overrides", {})
    )
    if _skip_rationing:
        sim.active_alerts.pop("rationing", None)
    else:
        check_rationing(sim.sensor_data["flow_rate"], sim=sim)

    return risk_cache


def _handle_motor_stuck_alert(
    sim: BuildingSimulator, var: str, value: object,
) -> None:
    if not hasattr(sim, "_alert_consecutive"):
        sim._alert_consecutive = {}
    if value:
        consecutive = sim._alert_consecutive.get(var, 0) + 1
        sim._alert_consecutive[var] = consecutive
        if consecutive >= ALERT_DEBOUNCE_TICKS:
            from apps.events.alerts.engine import send_alert
            from apps.events.services.alert_service import get_professional_action
            action = get_professional_action(var, RISK_CRITICO, value)
            send_alert(var, value, RISK_CRITICO, action, sim=sim)
    else:
        sim.active_alerts.pop(var, None)
        sim._alert_consecutive.pop(var, None)


def _handle_enum_alert(
    sim: BuildingSimulator, var: str, value: object,
) -> None:
    from apps.events.alerts.engine import send_alert
    from apps.events.services.alert_service import get_professional_action
    from apps.sensors.sensor_config import ENUM_RISK_VALUES, RISK_CRITICO, RISK_ALTO
    from apps.sensors.simulation.constants import MAX_DOOR_CLOSE_ATTEMPTS

    risky_values = ENUM_RISK_VALUES.get(var, set())
    str_val = str(value).lower() if value is not None else ""
    if str_val in risky_values:
        risk = RISK_CRITICO
        if var == "door_status":
            is_moving = sim._elev_state in ("ACCELERATING", "MOVING", "DECELERATING") or sim.sensor_data.get("speed", 0.0) > 0.05
            if str_val == "closing":
                if sim.door_close_attempts < 2:
                    risk = RISK_ALTO
            else:
                if not is_moving and sim.door_close_attempts < MAX_DOOR_CLOSE_ATTEMPTS:
                    sim.active_alerts.pop(var, None)
                    return
        action = get_professional_action(var, risk, value)
        send_alert(var, value, risk, action, sim=sim)
    else:
        sim.active_alerts.pop(var, None)


def _build_history_records(sim: BuildingSimulator, alert_vars: set[str], risk_cache: dict[str, str] = None) -> None:
    from apps.core.services.risk_service import classify_risk
    from apps.thresholds.services import get_thresholds

    thresholds = get_thresholds(sim.edificio_id)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    new_readings = []
    all_tracked_vars = set(alert_vars) | set(SYSTEM_VARS)
    for var, value in sim.sensor_data.items():
        if var not in all_tracked_vars:
            continue
        if risk_cache and var in risk_cache:
            risk = risk_cache[var]
        elif var not in BOOLEAN_VARS:
            risk, _ = classify_risk(
                var, value, thresholds,
                pump_on=sim.pump_on,
                speed=sim.sensor_data.get("speed", 0.0),
                door_close_attempts=sim.door_close_attempts,
                pos_stuck=getattr(sim, "_elev_pos_sensor_stuck", False),
                elevator_on=sim.elevator_on,
            )
        else:
            risk = RISK_CRITICO if value else RISK_NORMAL
        from apps.sensors.sensor_config import RISK_COLORS
        color = RISK_COLORS.get(risk, {}).get("email", {}).get("text", "#475569")
        sensor_type = "Bomba" if var in PUMP_VARS else "Elevador"
        new_readings.append({
            "timestamp": timestamp,
            "type": sensor_type,
            "variable": var,
            "value": value,
            "risk": risk,
            "color": color,
        })
    sim.history.extend(new_readings)
    if len(sim.history) > MAX_HISTORY_SIZE:
        sim.history = sim.history[-MAX_HISTORY_SIZE:]


def generate_data_and_emit() -> None:


    _consecutive_failures: dict[int, int] = {}
    _backoff_remaining: dict[int, int] = {}

    while True:
        eventlet.sleep(SIM_TICK_INTERVAL)
        for sim in list(simulators.values()):
            eid = sim.edificio_id

            if _backoff_remaining.get(eid, 0) > 0:
                _backoff_remaining[eid] -= 1
                continue

            try:
                _run_sim_tick(sim)
                _consecutive_failures.pop(eid, None)
                _backoff_remaining.pop(eid, None)
            except Exception:
                fails = _consecutive_failures.get(eid, 0) + 1
                _consecutive_failures[eid] = fails
                logger.exception(
                    "Error en tick de sim %s (%s) — fallo consecutivo #%s",
                    eid, sim.nombre, fails,
                )
                backoff = min(2 ** fails, _MAX_BACKOFF_TICKS)
                _backoff_remaining[eid] = backoff
                logger.warning(
                    "Simulador %s (%s) en backoff por %s ticks — reintentará automáticamente",
                    eid, sim.nombre, backoff,
                )
