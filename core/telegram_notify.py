# core/telegram_notify.py
import urllib.request
import urllib.parse
import json
import threading
from django.conf import settings

def _do_send_telegram_msg(chat_id, text, button_text=None, button_url=None):
    if not chat_id or not getattr(settings, 'TELEGRAM_BOT_TOKEN', None):
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    if button_text and button_url:
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
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"⚠️ Error en envío asíncrono Telegram: {e}")
        return False

def send_telegram_msg(chat_id, text, button_text=None, button_url=None, sync=False):
    """
    Envía mensajes a Telegram. Por defecto lo hace en segundo plano (daemon thread)
    para no retrasar respuestas HTTP ni congelar el frontend.
    """
    if sync:
        return _do_send_telegram_msg(chat_id, text, button_text, button_url)
    
    # Despachar en hilo secundario no bloqueante
    t = threading.Thread(
        target=_do_send_telegram_msg,
        args=(chat_id, text, button_text, button_url),
        daemon=True
    )
    t.start()
    return True