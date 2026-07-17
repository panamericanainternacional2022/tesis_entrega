from django.core.cache import cache

from apps.history.shared import _build_history_query

_UNREAD_CACHE_TTL = 2


def unread_history_count(request):
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return {"unread_history_count": 0}

    cache_key = f"unread_count_{usuario_id}"
    count = cache.get(cache_key)
    if count is None:
        rol = request.session.get("usuario_rol", "US")
        records, _ = _build_history_query(usuario_id, rol)
        count = records.filter(resolved=False).distinct().count()
        cache.set(cache_key, count, timeout=_UNREAD_CACHE_TTL)
    return {"unread_history_count": count}
