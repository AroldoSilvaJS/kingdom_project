# core/middleware.py
from django.shortcuts import render
from django.conf import settings
from core.telegram_auth import is_user_in_group
from core.models import UserRole

ADMIN_TG_ID = '7474444797'

class TelegramSessionMiddleware:
    """
    1. Aísla las sesiones por cada tg_id.
    2. Blindaje de seguridad: Bloquea a usuarios fuera del grupo.
    3. ⚖️ Mazmorra Imperial: Bloquea a usuarios con ban activo.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_id = request.GET.get('tg_id') or request.POST.get('tg_id')

        if incoming_id and str(incoming_id).strip() not in ['', 'None', 'undefined', 'null']:
            try:
                clean_id = int(incoming_id)
                if request.session.get('tg_id') != clean_id:
                    request.session['tg_id'] = clean_id
            except (ValueError, TypeError):
                pass

        # Rutas exentas (Admin, Webhooks, Archivos estáticos y Pago de Fianza)
        exempt_paths = ['/admin/', '/telegram-webhook/', '/static/', '/media/', '/economy/bazar/buy/']
        if any(request.path.startswith(p) for p in exempt_paths):
            return self.get_response(request)

        # Resolver el ID del usuario
        tg_id = request.session.get('tg_id') or incoming_id
        if tg_id and str(tg_id).isdigit():
            clean_id = int(tg_id)
            
            # 1. Filtro de Grupo
            if str(clean_id) != ADMIN_TG_ID and not is_user_in_group(clean_id):
                interview_link = getattr(settings, 'TELEGRAM_INTERVIEW_GROUP_URL', 'https://t.me/KingdomOfPleasureOf')
                return render(request, 'core/access_denied.html', {
                    'tg_id': clean_id,
                    'interview_url': interview_link,
                    'hide_bottom_nav': True
                }, status=403)

            # 2. ⚖️ MAZMORRA REAL: Si está baneado, enviarlo a prisión
            if str(clean_id) != ADMIN_TG_ID:
                role_obj = UserRole.objects.filter(telegram_id=clean_id).first()
                if role_obj and role_obj.is_banned:
                    from economy.models import Wallet
                    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=clean_id)
                    return render(request, 'core/dungeon.html', {
                        'tg_id': clean_id,
                        'user_role': role_obj,
                        'wallet': wallet,
                        'hide_bottom_nav': True
                    }, status=403)

        response = self.get_response(request)
        return response