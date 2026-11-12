# core/telegram_auth.py
import json
import urllib.request
import urllib.error
import sys
import time
from django.conf import settings
from django.core.cache import cache

ADMIN_TG_ID = '7474444797'

# Memoria local ultrarrápida en el proceso Gunicorn (TTL 1800s / 30 min)
# Evita depender únicamente de django.core.cache si no hay backend persistente
_LOCAL_MEM_CACHE = {}

def is_user_in_group(user_tg_id: int) -> bool:
    """
    Verifica con la API de Telegram si el usuario pertenece al grupo oficial.
    Utiliza doble caché en memoria (proceso + Django cache, 30 min)
    para eliminar llamadas HTTP síncronas que provocan lag en la WebApp.
    """
    if not user_tg_id:
        return False

    # 1. Pase libre inmediato para Administrador Supremo o Tests
    if 'test' in sys.argv or str(user_tg_id) == ADMIN_TG_ID:
        return True

    # Pase libre en desarrollo local
    if str(user_tg_id) == '123456789' and getattr(settings, 'DEBUG', False):
        return True

    now = time.time()
    # 2. Comprobar caché en memoria del proceso (0.01ms)
    local_entry = _LOCAL_MEM_CACHE.get(user_tg_id)
    if local_entry and local_entry[1] > now:
        return local_entry[0]

    # 3. Comprobar caché de Django
    cache_key = f"tg_member_status_{user_tg_id}"
    try:
        cached_status = cache.get(cache_key)
        if cached_status is not None:
            _LOCAL_MEM_CACHE[user_tg_id] = (cached_status, now + 1800)
            return cached_status
    except Exception:
        pass

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
        # Timeout a 2.5s para no congelar la pantalla
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                status = data.get('result', {}).get('status')
                is_member = status in ['creator', 'administrator', 'member', 'restricted']
                _LOCAL_MEM_CACHE[user_tg_id] = (is_member, now + 1800)
                try:
                    cache.set(cache_key, is_member, timeout=1800)
                except Exception:
                    pass
                return is_member
            else:
                _LOCAL_MEM_CACHE[user_tg_id] = (False, now + 600)
                try:
                    cache.set(cache_key, False, timeout=600)
                except Exception:
                    pass
                return False
    except urllib.error.HTTPError as e:
        if e.code == 400:
            _LOCAL_MEM_CACHE[user_tg_id] = (False, now + 600)
            try:
                cache.set(cache_key, False, timeout=600)
            except Exception:
                pass
            return False
        print(f"⚠️ Error HTTP getChatMember para {user_tg_id}: {e}")
    except Exception as e:
        print(f"⚠️ Error general getChatMember para {user_tg_id}: {e}")

    # En caso de error de red transitorio, no bloquear al usuario legítimo
    return True
