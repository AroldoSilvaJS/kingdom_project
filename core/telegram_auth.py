# core/telegram_auth.py
# core/telegram_auth.py
import json
import urllib.request
import urllib.error
from django.conf import settings
import sys

ADMIN_TG_ID = '7474444797'

def is_user_in_group(user_tg_id: int) -> bool:
    """
    Verifica con la API de Telegram si el usuario pertenece al grupo oficial.
    Retorna True si es miembro activo, False si es un extraño o fue expulsado.
    """
    if not user_tg_id:
        return False

    # 1. En tests o si es el Administrador Supremo, pase libre
    if 'test' in sys.argv or str(user_tg_id) == ADMIN_TG_ID:
        return True

    # Si es el ID de desarrollo local (123456789), permitir pase si DEBUG es True
    if str(user_tg_id) == '123456789' and getattr(settings, 'DEBUG', False):
        return True

    bot_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
    group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)

    if not bot_token or not group_id:
        return True # Si no está configurado, no bloquear

    url = f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={group_id}&user_id={user_tg_id}"

    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'KingdomBot/2.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                status = data.get('result', {}).get('status')
                print(f"✅ Telegram getChatMember para {user_tg_id}: Estatus = {status}")
                return status in ['creator', 'administrator', 'member', 'restricted']
            else:
                print(f"⚠️ Telegram getChatMember falló: {data}")
    except urllib.error.HTTPError as e:
        error_content = e.read().decode('utf-8')
        print(f"❌ Error HTTP de Telegram getChatMember ({e.code}): {error_content}")
        # Si Telegram dice "user not found" es porque ese ID numérico no está en el grupo
    except Exception as e:
        print(f"⚠️ Excepción consultando grupo: {e}")

    return False