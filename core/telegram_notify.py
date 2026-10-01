# core/telegram_notify.py
import urllib.request
import urllib.parse
import json
from django.conf import settings

def send_telegram_msg(chat_id, text, button_text=None, button_url=None):
    """
    Envía un mensaje formal de la Corona al chat o grupo de Telegram.
    """
    if not chat_id or not settings.TELEGRAM_BOT_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    if button_text and button_url:
        # Si chat_id es negativo, es un GRUPO (se usa 'url')
        # Si chat_id es positivo, es un PRIVADO (se usa 'web_app')
        is_group = int(chat_id) < 0
        btn_dict = {'text': button_text}
        
        if is_group:
            btn_dict['url'] = button_url
        else:
            btn_dict['web_app'] = {'url': button_url}

        payload['reply_markup'] = {
            'inline_keyboard': [[btn_dict]]
        }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
        
    # ✅ REEMPLAZAR POR:
    except urllib.error.HTTPError as e:
        error_detalle = e.read().decode('utf-8')
        print(f"❌ Error Telegram API ({e.code}): {error_detalle}")
        return False
    except Exception as e:
        print(f"⚠️ Error general en send_telegram_msg: {e}")
        return False