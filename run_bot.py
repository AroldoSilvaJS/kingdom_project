import os
import django

# 1. Inicializar Django para tener acceso a los modelos y settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import time
import requests
from django.conf import settings

TOKEN = settings.TELEGRAM_BOT_TOKEN
# URL pública de tu aplicación (por ejemplo tu túnel Cloudflare o Pinggy)
# Si estás en desarrollo local, pon tu URL pública de Cloudflare/Pinggy
WEBAPP_URL = "https://tu-url-de-cloudflare-o-pinggy.trycloudflare.com"

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {'timeout': 30, 'offset': offset}
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json().get('result', [])
    except Exception:
        return []

def send_welcome(chat_id, user_first_name, is_group=False):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    if is_group:
        # En grupos, Telegram no permite abrir WebApps directamente en el chat grupal por seguridad.
        # Se envía un botón con enlace que abre la WebApp o redirige al privado.
        texto = (
            f"👑 <b>¡Saludos, {user_first_name}!</b>\n\n"
            f"Las puertas de <b>Kingdom of Pleasure</b> están abiertas para los miembros de este círculo privado.\n\n"
            f"Toca el botón inferior para ingresar al Reino."
        )
        reply_markup = {
            'inline_keyboard': [[
                {'text': '✨ Entrar al Kingdom of Pleasure', 'url': f"https://t.me/TuBotAlias?start=menu"}
            ]]
        }
    else:
        # En chat privado, abre directamente la Mini App integrada
        texto = (
            f"👑 <b>Bienvenido al Kingdom of Pleasure, {user_first_name}.</b>\n\n"
            f"El círculo más exclusivo de rol y tentaciones te espera.\n"
            f"Pulsa el botón dorado para cruzar el umbral."
        )
        reply_markup = {
            'inline_keyboard': [[
                {'text': '🌹 Abrir Kingdom WebApp', 'web_app': {'url': WEBAPP_URL}}
            ]]
        }

    payload = {
        'chat_id': chat_id,
        'text': texto,
        'parse_mode': 'HTML',
        'reply_markup': reply_markup
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def main():
    print("🤖 Bot de Kingdom of Pleasure iniciado y escuchando comandos...")
    offset = None
    
    while True:
        updates = get_updates(offset)
        for u in updates:
            offset = u['update_id'] + 1
            msg = u.get('message')
            if not msg:
                continue

            text = msg.get('text', '').strip()
            chat = msg.get('chat', {})
            chat_id = chat.get('id')
            chat_type = chat.get('type') # 'private', 'group', o 'supergroup'
            user = msg.get('from', {})
            first_name = user.get('first_name', 'Noble')

            # Si el mensaje empieza con /start
            if text.startswith('/start'):
                is_group = chat_type in ['group', 'supergroup']
                send_welcome(chat_id, first_name, is_group=is_group)

        time.sleep(1)

if __name__ == '__main__':
    main()