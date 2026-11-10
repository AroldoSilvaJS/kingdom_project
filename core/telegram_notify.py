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

    # Enrutamiento automático al Tema/Topic oficial del Reino si el destino es el Grupo
    group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)
    if message_thread_id is None and group_id and str(chat_id) == str(group_id):
        default_topic = getattr(settings, 'TELEGRAM_TOPIC_ID', None)
        if default_topic:
            message_thread_id = default_topic

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    # Si se envía a un tema/foro específico (message_thread_id)
    if message_thread_id:
        try:
            tid = int(message_thread_id)
            if tid > 0:
                payload['message_thread_id'] = tid
        except (ValueError, TypeError):
            pass

    if button_text and button_url:
        try:
            is_group = int(chat_id) < 0
        except (ValueError, TypeError):
            is_group = str(chat_id).startswith('-')
            
        btn_dict = {'text': button_text}
        
        # Telegram Bot API prohíbe dominios t.me dentro de web_app:
        is_telegram_link = ('t.me/' in button_url) or ('telegram.me/' in button_url)
        if is_group or is_telegram_link:
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