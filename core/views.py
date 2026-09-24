from urllib.parse import quote as encode_param
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import F, Sum, Count
from django.utils import timezone
from datetime import timedelta

# Modelos de tus apps reales
from core.models import UserRole, UserProfile, KingdomSetting, AdminAuditLog
from economy.models import Wallet
from idols.models import IdolProfile, PostUnlock
from pets.models import Pet

# ID Maestro del Administrador de Telegram
ADMIN_TG_ID = '7474444797'

def admin_required(view_func):
    """Decorador de seguridad: solo administradores pueden entrar."""
    def _wrapped_view(request, *args, **kwargs):
        tg_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
        if not tg_id:
            return redirect('/')
        try:
            tg_id = str(tg_id)
        except ValueError:
            return redirect('/')
            
        # Permitir si coincide con el ID maestro o si tiene rol 'admin' en la base de datos
        is_admin = (tg_id == ADMIN_TG_ID) or UserRole.objects.filter(telegram_id=tg_id, role='admin').exists()
        if not is_admin:
            messages.error(request, "Alto ahí, súbdito. Esta sala está reservada a la Corona.")
            return redirect(f'/?tg_id={tg_id}')
        return view_func(request, int(tg_id), *args, **kwargs)
    return _wrapped_view

@admin_required
def admin_panel(request, admin_tg_id):
    """Panel de Administrador Supremo con control total de súbditos y economía."""
    if request.method == "POST":
        accion = request.POST.get('accion')

        # 1. MODIFICAR SALDO INDIVIDUAL (+, -, o fijar)
        if accion == 'adjust_gold':
            target_id = int(request.POST.get('target_id'))
            mode = request.POST.get('mode', 'add')
            amount = int(request.POST.get('amount', 0))
            wallet, _ = Wallet.objects.get_or_create(telegram_user_id=target_id)
            
            if mode == 'add':
                wallet.add_funds(amount)
                msg = f"+{amount} 🪙 otorgados a {target_id}"
            elif mode == 'subtract':
                wallet.remove_funds(amount)
                msg = f"-{amount} 🪙 retirados a {target_id}"
            else:
                wallet.balance = max(0, amount)
                wallet.save()
                msg = f"Saldo fijado en {amount} 🪙 para {target_id}"
            
            AdminAuditLog.objects.create(admin_tg_id=admin_tg_id, action='gold_adjust', target_tg_id=target_id, details=msg)
            messages.success(request, msg)
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 2. LLUVIA DE ORO MASIVA (a todos los ciudadanos no baneados)
        elif accion == 'mass_gold':
            amount = int(request.POST.get('amount', 0))
            if amount > 0:
                banned_ids = list(UserRole.objects.filter(is_banned=True).values_list('telegram_id', flat=True))
                count = Wallet.objects.exclude(telegram_user_id__in=banned_ids).update(balance=F('balance') + amount)
                AdminAuditLog.objects.create(admin_tg_id=admin_tg_id, action='mass_gold', details=f"Lluvia: +{amount} 🪙 a {count} usuarios")
                messages.success(request, f"✨ ¡Lluvia consumada! +{amount} 🪙 entregados a {count} súbditos.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 3. CAMBIAR ROL (admin, moderador, idol, vip, cliente)
        elif accion == 'change_role':
            target_id = int(request.POST.get('target_id'))
            new_role = request.POST.get('new_role')
            UserRole.objects.filter(telegram_id=target_id).update(role=new_role)
            messages.success(request, f"👑 Rol de {target_id} cambiado a {new_role}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 4. BANEAR O DESBANEAR
        elif accion == 'toggle_ban':
            target_id = int(request.POST.get('target_id'))
            user = get_object_or_404(UserRole, telegram_id=target_id)
            user.is_banned = not user.is_banned
            user.ban_reason = request.POST.get('ban_reason', 'Sanción disciplinaria') if user.is_banned else None
            user.save()
            messages.warning(request, f"⚖️ Usuario {target_id} {'BANEADO' if user.is_banned else 'DESBANEADO'}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 5. RESETEAR COOLDOWN DE BONO (24H) A UN USUARIO
        elif accion == 'reset_bonus':
            target_id = int(request.POST.get('target_id'))
            wallet = Wallet.objects.filter(telegram_user_id=target_id).first()
            if wallet:
                wallet.last_bonus_claim = None
                wallet.save()
                messages.success(request, f"⏱️ Cooldown de bono restablecido para {target_id}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 6. RESETEAR COOLDOWN DE BONO A TODOS LOS CIUDADANOS
        elif accion == 'reset_all_bonuses':
            Wallet.objects.all().update(last_bonus_claim=None)
            AdminAuditLog.objects.create(admin_tg_id=admin_tg_id, action='reset_all_bonuses', details="Perdón Real: Todos pueden reclamar bono")
            messages.success(request, "🎉 Cooldown de bono reseteado para todo el reino.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        # 7. ANUNCIO GLOBAL (DECRETO EN MARQUESINA)
        elif accion == 'broadcast_message':
            txt = request.POST.get('broadcast_text', '').strip()
            KingdomSetting.set_val('broadcast_message', txt)
            KingdomSetting.set_val('broadcast_active', 'true' if request.POST.get('is_active') == '1' else 'false')
            messages.success(request, "📢 Decreto global actualizado.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

    # =========================================================================
    # LECTURA OPTIMIZADA O(1) (Sin consultas lentas ni N+1)
    # =========================================================================
    usuarios_roles = UserRole.objects.all().order_by('-id')
    user_ids = [u.telegram_id for u in usuarios_roles]

    wallets_map = {w.telegram_user_id: w for w in Wallet.objects.filter(telegram_user_id__in=user_ids)}
    profiles_map = {p.telegram_user_id: p for p in UserProfile.objects.filter(telegram_user_id__in=user_ids)}

    total_oro = 0
    total_bans = 0
    for u in usuarios_roles:
        w = wallets_map.get(u.telegram_id)
        u.balance = w.balance if w else 0
        u.profile = profiles_map.get(u.telegram_id)
        # can_claim_bonus ya existe en tu modelo Wallet de economy
        u.has_bonus_cooldown = not w.can_claim_bonus() if w else False
        total_oro += u.balance
        if u.is_banned:
            total_bans += 1

    idols = IdolProfile.objects.all()
    broadcast_msg = KingdomSetting.get_val('broadcast_message', '')
    broadcast_active = KingdomSetting.get_val('broadcast_active', 'false') == 'true'

    return render(request, 'core/admin_panel.html', {
        'admin_tg_id': admin_tg_id,
        'usuarios': usuarios_roles,
        'idols': idols,
        'total_usuarios': len(usuarios_roles),
        'total_oro': total_oro,
        'total_baneados': total_bans,
        'broadcast_msg': broadcast_msg,
        'broadcast_active': broadcast_active,
    })


def main_menu(request):
    raw_id = request.GET.get('tg_id') or request.session.get('tg_id')
    tg_id = raw_id if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null'] else '123456789'
    
    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    role = role_obj.role if role_obj else 'cliente'
    is_admin = (str(tg_id) == ADMIN_TG_ID) or (role == 'admin')

    return render(request, 'core/menu.html', {
        'tg_id': tg_id,
        'role': role,
        'is_admin': is_admin,
    })


def leaderboard(request):
    tg_id = request.GET.get('tg_id') or request.session.get('tg_id')

    # 1. TOP IDOLS: Ordenadas por desbloqueos de sus fotos VIP y likes
    top_idols = IdolProfile.objects.annotate(
        total_unlocks=Count('posts__unlocks', distinct=True),
        total_likes=Sum('posts__likes')
    ).order_by('-total_unlocks', '-rating')[:10]

    for idol in top_idols:
        idol.likes_count = idol.total_likes or 0

    # 2. TOP MAGNATES: Clientes con más oro en su Bóveda
    top_wallets = Wallet.objects.order_by('-balance')[:10]
    
    titulos = ["👑 Emperador Clandestino", "💎 Duque de Oro", "🥂 Lord del Placer", "✨ Barón VIP", "🎩 Caballero del Reino"]
    magnates = []
    for idx, w in enumerate(top_wallets):
        magnates.append({
            'telegram_id': str(w.telegram_user_id)[-4:],
            'full_id': w.telegram_user_id,
            'balance': w.balance,
            'titulo': titulos[idx] if idx < len(titulos) else "Ciudadano Honorable"
        })

    return render(request, 'core/leaderboard.html', {
        'tg_id': tg_id,
        'top_idols': top_idols,
        'magnates': magnates
    })


def my_profile(request):
    raw_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
    tg_id = raw_id if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null'] else None
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or 'Noble Anónimo'
    
    if not tg_id:
        return redirect('/')
        
    profile, _ = UserProfile.objects.get_or_create(
        telegram_user_id=tg_id,
        defaults={'username': tg_username}
    )
    
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    all_idols = IdolProfile.objects.all().order_by('stage_name')

    if request.method == 'POST':
        profile.username = request.POST.get('username', profile.username)
        profile.title = request.POST.get('title', profile.title)
        profile.bio = request.POST.get('bio', '')
        profile.avatar_frame = request.POST.get('avatar_frame', profile.avatar_frame)
        profile.motto = request.POST.get('motto', profile.motto)
        profile.profile_theme = request.POST.get('profile_theme', profile.profile_theme)
        profile.vip_badge = request.POST.get('vip_badge', profile.vip_badge)
        
        fav_id = request.POST.get('favorite_idol')
        if fav_id:
            profile.favorite_idol = IdolProfile.objects.filter(id=fav_id).first()
        else:
            profile.favorite_idol = None
            
        profile.save()
        messages.success(request, "¡Tu Pasaporte Noble ha sido actualizado con éxito!")
        return redirect(f'/profile/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')

    return render(request, 'core/profile.html', {
        'tg_id': tg_id,
        'profile': profile,
        'wallet': wallet,
        'pet': pet,
        'all_idols': all_idols,
    })