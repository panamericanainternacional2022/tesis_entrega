from apps.history.shared import _build_history_query


def unread_history_count(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return {"unread_history_count": 0}

    rol = request.session.get("usuario_rol", "US")

    records, _ = _build_history_query(usuario_id, rol)

    records_count = records.distinct().count()

    return {"unread_history_count": records_count}
