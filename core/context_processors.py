# core/context_processors.py
from idols.models import CustomRequest, IdolProfile
from core.models import UserRole, KingdomSetting

ADMIN_TG_ID = '7474444797'

def kingdom_notifications(request):
    raw_id = (
        request.GET.get('tg_id') or 
        request.POST.get('tg_id') or 
        request.COOKIES.get('tg_id') or 
        request.session.get('tg_id')
    )

    # 📢 Decreto Público Imperial (Global para toda la app)
    broadcast_active = KingdomSetting.get_val('broadcast_active', 'false') == 'true'
    broadcast_msg = KingdomSetting.get_val('broadcast_message', '')

    context = {
        'broadcast_active': broadcast_active,
        'broadcast_message': broadcast_msg,
        'unread_notifications_count': 0
    }

    if not raw_id or str(raw_id).strip() in ['', 'None', 'undefined', 'null']:
        return context

    try:
        tg_id = int(raw_id)
    except (ValueError, TypeError):
        return context

    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    has_idols = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
    is_idol = (role_obj and role_obj.role == 'idol') or has_idols

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

    context['unread_notifications_count'] = count
    return context