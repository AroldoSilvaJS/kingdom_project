# core/context_processors.py
from idols.models import CustomRequest
from core.models import UserRole

ADMIN_TG_ID = '7474444797'

def kingdom_notifications(request):
    """
    Calcula el badge de la campanita en tiempo real:
    - Para Idols: Antojos pendientes por atender.
    - Para Clientes: Antojos entregados listos para ver en su colección.
    """
    raw_id = (
        request.GET.get('tg_id') or 
        request.POST.get('tg_id') or 
        request.COOKIES.get('tg_id') or 
        request.session.get('tg_id')
    )
    if not raw_id or str(raw_id).strip() in ['', 'None', 'undefined', 'null']:
        return {'unread_notifications_count': 0}

    try:
        tg_id = int(raw_id)
    except (ValueError, TypeError):
        return {'unread_notifications_count': 0}

    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    is_idol = (role_obj and role_obj.role == 'idol')

    count = 0
    if is_idol:
        count = CustomRequest.objects.filter(
            idol__telegram_user_id=tg_id, 
            status='pending'
        ).count()
    else:
        count = CustomRequest.objects.filter(
            client_telegram_id=tg_id,
            status='accepted'
        ).count()

    return {'unread_notifications_count': count}