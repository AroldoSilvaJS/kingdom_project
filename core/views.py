from django.shortcuts import render, redirect
from idols.models import UserRole
from economy.models import Wallet

# 👑 Tu ID Maestro de Telegram
ADMIN_TG_ID = '7474444797'

def main_menu(request):
    # 1. Buscamos el ID en la URL, POST, o sesión
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
    
    # 2. Si el usuario acaba de elegir su rol:
    if request.method == 'POST':
        elegido = request.POST.get('role')
        if elegido and tg_id and tg_id != "None":
            UserRole.objects.update_or_create(
                telegram_id=tg_id,
                defaults={'role': elegido}
            )
            request.session['tg_id'] = tg_id
            return redirect(request.path)

    # 3. Buscamos si este usuario ya tiene rol:
    usuario = None
    if tg_id and tg_id != "None":
        request.session['tg_id'] = tg_id
        usuario = UserRole.objects.filter(telegram_id=tg_id).first()
    
    # 4. Si NO tiene rol, le mostramos la pantalla de elección:
    if not usuario:
        return render(request, 'idols/choose_role.html', {'tg_id': tg_id})

    # 5. Verificamos si el que entró eres TÚ
    es_admin = (tg_id == ADMIN_TG_ID)

    # 6. Lo dejamos entrar al menú:
    return render(request, 'core/menu.html', {
        'tg_id': tg_id,
        'role': usuario.role,
        'is_admin': es_admin  # <- Enviamos la llave al HTML
    })
    
def admin_panel(request):
    # Buscamos quién intenta entrar
    tg_id = request.GET.get('tg_id') or request.session.get('tg_id')
    
    # CANDADO: Si no eres tú, patada de vuelta al inicio
    if str(tg_id) != ADMIN_TG_ID:
        return redirect(f"/?tg_id={tg_id}")
        
    # --- NUEVA LÓGICA DE PODERES ---
    if request.method == 'POST':
        action = request.POST.get('action')
        target_id = request.POST.get('target_id')
        
        if target_id:
            usuario_target = UserRole.objects.filter(telegram_id=target_id).first()
            if usuario_target:
                # Si apretaste "Cambiar Rol"
                if action == 'toggle_role':
                    usuario_target.role = 'cliente' if usuario_target.role == 'idol' else 'idol'
                    usuario_target.save()
            # Si apretaste "Expulsar"
                elif action == 'delete':
                    usuario_target.delete()
                
                # --- AGREGAR DESDE AQUÍ (GESTIÓN DE ORO) ---
                elif action in ['add_gold', 'remove_gold']:
                    try:
                        amount = int(request.POST.get('amount', 0))
                        if amount > 0:
                            wallet, _ = Wallet.objects.get_or_create(telegram_user_id=target_id)
                            if action == 'add_gold':
                                wallet.add_funds(amount)
                            elif action == 'remove_gold':
                                wallet.remove_funds(amount)
                    except ValueError:
                        pass
                # --- HASTA AQUÍ ---
                
        
        # Recargamos la página para ver los cambios
        return redirect(f"/admin-panel/?tg_id={tg_id}")
    # -------------------------------

  # Traemos a todos los usuarios de la base de datos
    todos_los_usuarios = UserRole.objects.all()

    # --- AGREGAR ESTAS LÍNEAS PARA LEER EL SALDO EN VIVO ---
    for u in todos_los_usuarios:
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=u.telegram_id)
        u.balance = wallet.balance
    # -------------------------------------------------------
    
    return render(request, 'core/admin_panel.html', {
        'usuarios': todos_los_usuarios,
        'tg_id': tg_id
    })