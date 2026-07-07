import datetime as dt

from apps.history.shared import _build_history_query


def unread_history_count(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return {"unread_history_count": 0}

    rol = request.session.get("usuario_rol", "US")

    records, _ = _build_history_query(usuario_id, rol)

    history_cleared_at = request.session.get("history_cleared_at")
    if history_cleared_at:
        cleared_dt = dt.datetime.fromtimestamp(history_cleared_at, tz=dt.timezone.utc)
        records = records.filter(date__gt=cleared_dt)

    records_count = records.distinct().count()

    return {"unread_history_count": records_count}
