from django.shortcuts import render

def main_menu(request):
    # Por ahora solo renderizamos el HTML. 
    # Más adelante aquí validaremos si el usuario viene de Telegram.
    return render(request, 'core/menu.html')