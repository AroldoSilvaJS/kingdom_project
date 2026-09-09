from django.shortcuts import render, redirect
from idols.models import UserRole  # Traemos el modelo que acabamos de crear

def main_menu(request):
    # 1. Obtenemos el ID de Telegram
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    
    # 2. Si el usuario acaba de presionar un botón para elegir su rol:
    if request.method == 'POST':
        elegido = request.POST.get('role')
        if elegido and tg_id:
            # Guardamos su elección en la base de datos
            UserRole.objects.create(telegram_id=tg_id, role=elegido)
            # Recargamos la misma página para que ahora lo deje entrar
            return redirect(f"{request.path}?tg_id={tg_id}")

    # 3. Buscamos si este usuario ya eligió su destino antes:
    usuario = None
    if tg_id:
        usuario = UserRole.objects.filter(telegram_id=tg_id).first()
    
    # 4. Si NO tiene rol, lo detenemos y le mostramos la pantalla de elección:
    if not usuario:
        return render(request, 'idols/choose_role.html', {'tg_id': tg_id})

    # 5. Si YA tiene rol, lo dejamos entrar al menú y le enviamos qué rol es:
    return render(request, 'core/menu.html', {
        'tg_id': tg_id,
        'role': usuario.role
    })