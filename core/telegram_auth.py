# core/telegram_auth.py
import json
import urllib.request
import urllib.error
import sys
from django.conf import settings
from django.core.cache import cache

ADMIN_TG_ID = '7474444797'

def is_user_in_group(user_tg_id: int) -> bool:
    """
    Verifica con la API de Telegram si el usuario pertenece al grupo oficial.
    Utiliza caché en memoria (30 min) para no saturar peticiones ni ralentizar la WebApp.
    """
    if not user_tg_id:
        return False

    # 1. Pase libre inmediato para Administrador Supremo o Tests
    if 'test' in sys.argv or str(user_tg_id) == ADMIN_TG_ID:
        return True

    # Pase libre en desarrollo local
    if str(user_tg_id) == '123456789' and getattr(settings, 'DEBUG', False):
        return True

    # 2. Comprobar si ya lo verificamos recientemente en caché (30 minutos)
    cache_key = f"tg_member_status_{user_tg_id}"
    cached_status = cache.get(cache_key)
    if cached_status is not None:
        return cached_status

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)

    if not bot_token or not group_id:
        return True

    url = f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={group_id}&user_id={user_tg_id}"

    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'KingdomBot/2.0'}
        )
        # Timeout reducido a 3s para evitar bloqueos largos
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                status = data.get('result', {}).get('status')
                is_member = status in ['creator', 'administrator', 'member', 'restricted']
                # Guardar resultado en caché por 30 minutos (1800 seg)
                cache.set(cache_key, is_member, timeout=1800)
                return is_member
    except Exception as e:
        print(f"⚠️ Error getChatMember para {user_tg_id}: {e}")

    # En caso de timeout transitorio de Telegram, no bloquear al usuario
    return True