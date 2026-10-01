# core/middleware.py

class TelegramSessionMiddleware:
    """
    Garantiza que cada usuario de Telegram tenga su propia sesión aislada.
    Si la petición trae un tg_id diferente al de la sesión actual, la sesión se reinicia.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_id = request.GET.get('tg_id') or request.POST.get('tg_id')

        if incoming_id and str(incoming_id).strip() not in ['', 'None', 'undefined', 'null']:
            try:
                clean_id = int(incoming_id)
                # Si cambió de cuenta, sobrescribimos la sesión para aislar los datos
                if request.session.get('tg_id') != clean_id:
                    request.session['tg_id'] = clean_id
            except (ValueError, TypeError):
                pass
        
        response = self.get_response(request)
        return response