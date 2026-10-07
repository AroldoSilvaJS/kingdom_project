# core/telegram_notify.py
import urllib.request
import urllib.parse
import json
import threading
from django.conf import settings

def _do_send_telegram_msg(chat_id, text, button_text=None, button_url=None, message_thread_id=None):
    if not chat_id or not getattr(settings, 'TELEGRAM_BOT_TOKEN', None):
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    # Si se envía a un tema/foro específico
    if message_thread_id:
        payload['message_thread_id'] = int(message_thread_id)

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

def send_telegram_msg(chat_id, text, button_text=None, button_url=None, message_thread_id=None, sync=False):
    """
    Envía mensajes a Telegram. Si message_thread_id está presente,
    el mensaje entra directamente al tema/topic correspondiente.
    """
    if sync:
        return _do_send_telegram_msg(chat_id, text, button_text, button_url, message_thread_id)
    
    t = threading.Thread(
        target=_do_send_telegram_msg,
        args=(chat_id, text, button_text, button_url, message_thread_id),
        daemon=True
    )
    t.start()
    return True