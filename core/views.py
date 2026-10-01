import json
from urllib.parse import quote as encode_param
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import F, Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from core.models import UserRole, UserProfile, KingdomSetting, AdminAuditLog
from economy.models import Wallet
from idols.models import IdolProfile, Post, PostUnlock, CustomRequest
from pets.models import Pet
from core.telegram_auth import is_user_in_group
from core.telegram_notify import send_telegram_msg

ADMIN_TG_ID = '7474444797'


def resolve_secure_tg_id(request):
    raw_id = (
        request.GET.get('tg_id') or 
        request.POST.get('tg_id') or 
        request.COOKIES.get('tg_id') or 
        request.session.get('tg_id')
    )
    if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null']:
        try:
            val = int(raw_id)
            request.session['tg_id'] = val
            return val
        except (ValueError, TypeError):
            pass

    return request.session.get('tg_id', 123456789)


def admin_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        tg_id = resolve_secure_tg_id(request)
        is_admin = (str(tg_id) == ADMIN_TG_ID) or UserRole.objects.filter(telegram_id=tg_id, role='admin').exists()
        if not is_admin:
            messages.error(request, "Alto ahí, forastero. Esta sala está reservada a la Corona.")
            return redirect(f'/?tg_id={tg_id}')
        return view_func(request, tg_id, *args, **kwargs)
    return _wrapped_view


@csrf_exempt
def main_menu(request):
    tg_id = resolve_secure_tg_id(request)

    if str(tg_id) != ADMIN_TG_ID and not is_user_in_group(tg_id):
        return render(request, 'core/access_denied.html', {'tg_id': tg_id})

    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    if not role_obj:
        return redirect(f'/choose-role/?tg_id={tg_id}')
    
    role = role_obj.role
    is_admin = (str(tg_id) == ADMIN_TG_ID) or (role == 'admin')
    has_idols_created = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
    is_idol = (role == 'idol') or has_idols_created or (str(tg_id) == ADMIN_TG_ID and has_idols_created)
    
    user_profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)

    if user_profile.username and not str(user_profile.username).lower().startswith('noble_'):
        clean_handle = user_profile.username if user_profile.username.startswith('@') else f"@{user_profile.username}"
        IdolProfile.objects.filter(telegram_user_id=tg_id).update(owner_username=clean_handle)

    return render(request, 'core/menu.html', {
        'tg_id': tg_id,
        'role': role,
        'is_idol': is_idol,
        'is_admin': is_admin,
        'user_profile': user_profile,
    })


def choose_role(request):
    tg_id = resolve_secure_tg_id(request)

    if str(tg_id) != ADMIN_TG_ID and not is_user_in_group(tg_id):
        return render(request, 'core/access_denied.html', {'tg_id': tg_id})

    
    existing_role = UserRole.objects.filter(telegram_id=tg_id).first()
    if existing_role and request.method != 'POST':
        return redirect(f'/?tg_id={tg_id}')

    if request.method == 'POST':
        selected_role = request.POST.get('role', 'cliente')
        real_tg_id = request.POST.get('tg_id') or tg_id
        clean_id = int(real_tg_id)
        
        request.session['tg_id'] = clean_id

        UserRole.objects.update_or_create(
            telegram_id=clean_id,
            defaults={'role': selected_role}
        )
        
        Wallet.objects.get_or_create(telegram_user_id=clean_id)
        UserProfile.objects.get_or_create(telegram_user_id=clean_id)
        
        tipo_nombre = "Idol Real 🌹" if selected_role == 'idol' else "Cliente VIP 🥂"
        messages.success(request, f"✨ ¡Bienvenido al Reino como {tipo_nombre}!")
        return redirect(f'/?tg_id={clean_id}')

    return render(request, 'idols/choose_role.html', {'tg_id': tg_id})


def my_profile(request):
    has_id = (
        request.GET.get('tg_id') or 
        request.POST.get('tg_id') or 
        request.COOKIES.get('tg_id') or 
        request.session.get('tg_id')
    )
    if not has_id or str(has_id).strip() in ['', 'None', 'undefined', 'null']:
        return redirect('/')

    tg_id = resolve_secure_tg_id(request)
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or f'Noble_{tg_id}'
    
    profile, _ = UserProfile.objects.get_or_create(
        telegram_user_id=tg_id,
        defaults={'username': tg_username}
    )
    
    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    if not role_obj:
        return redirect(f'/choose-role/?tg_id={tg_id}')

    has_idols_created = IdolProfile.objects.filter(telegram_user_id=tg_id).exists()
    is_idol = (role_obj.role == 'idol') or has_idols_created or (str(tg_id) == ADMIN_TG_ID and has_idols_created)
    
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    all_idols = IdolProfile.objects.all().order_by('stage_name')
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id)

    if request.method == 'POST':
        profile.username = request.POST.get('username', profile.username).strip()
        profile.title = request.POST.get('title', profile.title)
        profile.bio = request.POST.get('bio', '').strip()
        profile.avatar_frame = request.POST.get('avatar_frame', profile.avatar_frame)
        profile.motto = request.POST.get('motto', profile.motto).strip()
        profile.profile_theme = request.POST.get('profile_theme', profile.profile_theme)
        profile.vip_badge = request.POST.get('vip_badge', profile.vip_badge)
        
        if not is_idol:
            fav_id = request.POST.get('favorite_idol')
            profile.favorite_idol = IdolProfile.objects.filter(id=fav_id).first() if fav_id else None
            
        profile.save()
        mensaje = "✨ ¡Camerino de Musa actualizado con éxito!" if is_idol else "✨ ¡Pasaporte Noble actualizado con éxito!"
        messages.success(request, mensaje)
        return redirect(f'/profile/?tg_id={tg_id}&tg_username={encode_param(profile.username)}')

    total_servicios = sum(i.services_done for i in mis_idols)
    idol_posts = Post.objects.filter(idol__in=mis_idols)
    ventas_vip = PostUnlock.objects.filter(post__in=idol_posts).count()
    likes_totales = sum(p.likes for p in idol_posts)

    user_rank = profile.get_rank_name(is_idol=is_idol)
    unlocks_count = PostUnlock.objects.filter(client_telegram_id=tg_id).count()
    pet_level = pet.level if pet else 0
    pet_has_expedition = pet and pet.last_expedition is not None
    
    # --- ÁRBOL DE 12 LOGROS DINÁMICOS (IDOLS VS CLIENTES) ---
    if is_idol:
        achievements = [
            {'id': 'idol_born', 'name': 'Primera Huella', 'desc': 'Consagrar tu primer perfil de Idol en el Reino', 'icon': '🎭', 'unlocked': mis_idols.count() >= 1, 'progress': f"{mis_idols.count()}/1 Ficha"},
            {'id': 'idol_post', 'name': 'Sesión Inaugural', 'desc': 'Publicar tu primer post en el Muro', 'icon': '📸', 'unlocked': idol_posts.count() >= 1, 'progress': f"{idol_posts.count()}/1 Post"},
            {'id': 'idol_first_sale', 'name': 'Primera Venta VIP', 'desc': 'Lograr que un noble desbloquee tu contenido de pago', 'icon': '🔒', 'unlocked': ventas_vip >= 1, 'progress': f"{ventas_vip}/1 Venta"},
            {'id': 'idol_hot_seller', 'name': 'Musa Cotizada', 'desc': 'Alcanzar 5 ventas de contenido VIP en KingdomFans', 'icon': '💎', 'unlocked': ventas_vip >= 5, 'progress': f"{ventas_vip}/5 Ventas"},
            {'id': 'idol_wealth', 'name': 'Fortuna de la Noche', 'desc': 'Acumular al menos 1,000 🪙 de ganancias en tu Bóveda', 'icon': '🏦', 'unlocked': wallet.balance >= 1000, 'progress': f"{wallet.balance}/1000 🪙"},
            {'id': 'idol_drinks', 'name': 'Copas de Adhesión', 'desc': 'Recibir invitaciones de tragos o propinas de admiradores', 'icon': '🥂', 'unlocked': total_servicios >= 1, 'progress': f"{total_servicios}/1 Rol"},
            {'id': 'idol_first_5star', 'name': 'Ovación Estelar', 'desc': 'Recibir una reseña perfecta de 5 estrellas', 'icon': '⭐', 'unlocked': any(i.rating >= 4.9 for i in mis_idols), 'progress': "5.0★ Obtenida" if any(i.rating >= 4.9 for i in mis_idols) else "Pendiente"},
            {'id': 'idol_antojo_delivered', 'name': 'Deseo Satisfecho', 'desc': 'Completar y entregar una petición de Antojo Personalizado', 'icon': '🔥', 'unlocked': CustomRequest.objects.filter(idol__in=mis_idols, status='accepted').exists(), 'progress': "Completado" if CustomRequest.objects.filter(idol__in=mis_idols, status='accepted').exists() else "0/1 Pendiente"},
            {'id': 'idol_double_trouble', 'name': 'Doble Identidad', 'desc': 'Mantener activas tus 2 fichas de Idols oficiales', 'icon': '👑', 'unlocked': mis_idols.count() >= 2, 'progress': f"{mis_idols.count()}/2 Musas"},
            {'id': 'idol_pet_charm', 'name': 'Familiar Escénico', 'desc': 'Entrenar a tu mascota hasta Nivel 5 para potenciar tu carisma', 'icon': '🐾', 'unlocked': pet_level >= 5, 'progress': f"Lvl {pet_level}/5"},
            {'id': 'idol_star_30', 'name': 'Diva Consagrada', 'desc': 'Alcanzar el Nivel 25 de estrellato en el Reino', 'icon': '💄', 'unlocked': profile.level >= 25, 'progress': f"Lvl {profile.level}/25"},
            {'id': 'idol_legend_50', 'name': 'Diosa del Olimpo', 'desc': 'Alcanzar el legendario Nivel 50 de reputación absoluta', 'icon': '⚜️', 'unlocked': profile.level >= 50, 'progress': f"Lvl {profile.level}/50"},
        ]
    else:
        achievements = [
            {'id': 'gold_novice', 'name': 'Primer Arca', 'desc': 'Alcanzar una fortuna de al menos 300 🪙 en Bóveda', 'icon': '🪙', 'unlocked': wallet.balance >= 300, 'progress': f"{wallet.balance}/300 🪙"},
            {'id': 'gold_midas', 'name': 'Bóveda de Midas', 'desc': 'Acumular una fortuna de al menos 1,500 🪙', 'icon': '🏦', 'unlocked': wallet.balance >= 1500, 'progress': f"{wallet.balance}/1500 🪙"},
            {'id': 'gold_emperor', 'name': 'Emperador del Tesoro', 'desc': 'Alcanzar la legendaria cifra de 5,000 🪙 en Bóveda', 'icon': '💰', 'unlocked': wallet.balance >= 5000, 'progress': f"{wallet.balance}/5000 🪙"},
            {'id': 'court_iniciado', 'name': 'Bautismo Real', 'desc': 'Alcanzar el Nivel 5 en el Reino del Placer', 'icon': '✨', 'unlocked': profile.level >= 5, 'progress': f"Lvl {profile.level}/5"},
            {'id': 'court_noble', 'name': 'Caballero Consagrado', 'desc': 'Alcanzar el Nivel 15 de linaje imperial', 'icon': '🥂', 'unlocked': profile.level >= 15, 'progress': f"Lvl {profile.level}/15"},
            {'id': 'court_legend', 'name': 'Leyenda de la Corte', 'desc': 'Alcanzar el prestigioso Nivel 30', 'icon': '👑', 'unlocked': profile.level >= 30, 'progress': f"Lvl {profile.level}/30"},
            {'id': 'beast_tamer', 'name': 'Domador de Bestias', 'desc': 'Despertar a tu compañero espiritual en el Santuario', 'icon': '🥚', 'unlocked': pet is not None, 'progress': "1/1 Adoptado" if pet else "0/1 Pendiente"},
            {'id': 'beast_explorer', 'name': 'Paso por las Sombras', 'desc': 'Enviar a tu mascota a su primera expedición al bosque', 'icon': '🌲', 'unlocked': bool(pet_has_expedition), 'progress': "Completado" if pet_has_expedition else "Pendiente"},
            {'id': 'beast_alpha', 'name': 'Vínculo Ancestral', 'desc': 'Elevar a tu mascota espiritual al Nivel 5 o superior', 'icon': '🐾', 'unlocked': pet_level >= 5, 'progress': f"Lvl {pet_level}/5"},
            {'id': 'supporter_first', 'name': 'Primer Deleite', 'desc': 'Desbloquear tu primera foto privada en KingdomFans', 'icon': '🔞', 'unlocked': unlocks_count >= 1, 'progress': f"{unlocks_count}/1 Foto"},
            {'id': 'star_prestige', 'name': 'Mecenas Supremo', 'desc': 'Coleccionar al menos 10 fotos exclusivas en tu Colección', 'icon': '💎', 'unlocked': unlocks_count >= 10, 'progress': f"{unlocks_count}/10 Fotos"},
            {'id': 'devotion_mark', 'name': 'Pacto Eterno', 'desc': 'Consagrar tu corazón eligiendo a tu Musa Favorita oficial', 'icon': '🌹', 'unlocked': profile.favorite_idol is not None, 'progress': "Consagrado" if profile.favorite_idol is not None else "Pendiente"},
        ]

    return render(request, 'core/profile.html', {
        'tg_id': tg_id,
        'profile': profile,
        'wallet': wallet,
        'pet': pet,
        'all_idols': all_idols,
        'mis_idols': mis_idols,
        'is_idol': is_idol,
        'user_rank': user_rank,
        'total_servicios': total_servicios,
        'ventas_vip': ventas_vip,
        'likes_totales': likes_totales,
        'achievements': achievements,
        'unlocks_count': unlocks_count,
    })


def leaderboard(request):
    tg_id = resolve_secure_tg_id(request)

    top_idols = IdolProfile.objects.annotate(
        total_unlocks=Count('posts__unlocks', distinct=True),
        total_likes=Sum('posts__likes')
    ).order_by('-total_unlocks', '-rating')[:10]

    top_wallets = Wallet.objects.order_by('-balance')[:10]
    user_ids = [w.telegram_user_id for w in top_wallets]
    profiles_dict = {p.telegram_user_id: p for p in UserProfile.objects.filter(telegram_user_id__in=user_ids)}

    magnates = []
    for w in top_wallets:
        prof = profiles_dict.get(w.telegram_user_id)
        titulo = prof.get_rank_name() if prof else "Ciudadano Honorable"
        nivel = prof.level if prof else 1
        
        magnates.append({
            'telegram_id': str(w.telegram_user_id)[-4:],
            'full_id': w.telegram_user_id,
            'balance': w.balance,
            'titulo': titulo,
            'nivel': nivel,
        })

    return render(request, 'core/leaderboard.html', {
        'tg_id': tg_id,
        'top_idols': top_idols,
        'magnates': magnates
    })


@admin_required
def admin_panel(request, admin_tg_id):
    if request.method == "POST":
        accion = request.POST.get('accion')

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

        elif accion == 'purge_test_data':
            from idols.models import Review, Post, PostUnlock, PostLike, CustomRequest, PostComment
            PostComment.objects.all().delete()
            PostUnlock.objects.all().delete()
            PostLike.objects.all().delete()
            CustomRequest.objects.all().delete()
            Review.objects.all().delete()
            Post.objects.all().delete()
            IdolProfile.objects.all().delete()
            Pet.objects.all().delete()

            UserRole.objects.exclude(telegram_id=7474444797).delete()
            UserProfile.objects.exclude(telegram_user_id=7474444797).delete()
            Wallet.objects.exclude(telegram_user_id=7474444797).delete()

            UserRole.objects.update_or_create(telegram_id=7474444797, defaults={'role': 'admin'})
            w, _ = Wallet.objects.get_or_create(telegram_user_id=7474444797)
            w.balance = 1000
            w.save()

            messages.success(request, "🧹 ¡Purga completada! Todos los usuarios de prueba, idols y datos viejos fueron eliminados. Solo queda la Corona.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'mass_gold':
            amount = int(request.POST.get('amount', 0))
            if amount > 0:
                banned_ids = list(UserRole.objects.filter(is_banned=True).values_list('telegram_id', flat=True))
                count = Wallet.objects.exclude(telegram_user_id__in=banned_ids).update(balance=F('balance') + amount)
                messages.success(request, f"✨ ¡Lluvia consumada! +{amount} 🪙 entregados a {count} súbditos.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'change_role':
            target_id = int(request.POST.get('target_id'))
            new_role = request.POST.get('new_role')
            UserRole.objects.filter(telegram_id=target_id).update(role=new_role)
            messages.success(request, f"👑 Rango de {target_id} actualizado a {new_role.upper()}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'toggle_ban':
            target_id = int(request.POST.get('target_id'))
            user = get_object_or_404(UserRole, telegram_id=target_id)
            user.is_banned = not user.is_banned
            user.ban_reason = request.POST.get('ban_reason', 'Sanción de la Corona') if user.is_banned else None
            user.save()
            messages.warning(request, f"⚖️ Usuario {target_id} {'BANEADO' if user.is_banned else 'DESBANEADO'}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'reset_bonus':
            target_id = int(request.POST.get('target_id'))
            wallet = Wallet.objects.filter(telegram_user_id=target_id).first()
            if wallet:
                wallet.last_bonus_claim = None
                wallet.save()
                messages.success(request, f"⏱️ Cooldown de bono restablecido para {target_id}.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'reset_all_bonuses':
            Wallet.objects.all().update(last_bonus_claim=None)
            messages.success(request, "🎉 Cooldown de bono reseteado para todo el reino.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

        elif accion == 'broadcast_message':
            txt = request.POST.get('broadcast_text', '').strip()
            KingdomSetting.set_val('broadcast_message', txt)
            KingdomSetting.set_val('broadcast_active', 'true' if request.POST.get('is_active') == '1' else 'false')
            messages.success(request, "📢 Decreto global actualizado.")
            return redirect(f"{request.path}?tg_id={admin_tg_id}")

    usuarios_roles = list(UserRole.objects.all().order_by('-id'))
    user_ids = [u.telegram_id for u in usuarios_roles]

    wallets_map = {w.telegram_user_id: w for w in Wallet.objects.filter(telegram_user_id__in=user_ids)}
    profiles_map = {p.telegram_user_id: p for p in UserProfile.objects.filter(telegram_user_id__in=user_ids)}
    idols_map = {}
    for i in IdolProfile.objects.filter(telegram_user_id__in=user_ids):
        idols_map.setdefault(i.telegram_user_id, []).append(i.stage_name)

    total_oro = 0
    total_bans = 0
    for u in usuarios_roles:
        w = wallets_map.get(u.telegram_id)
        prof = profiles_map.get(u.telegram_id)
        
        u.balance = w.balance if w else 0
        u.profile = prof
        u.display_name = prof.username if (prof and prof.username) else f"Noble_{str(u.telegram_id)[-4:]}"
        u.display_username = f"@{prof.username.replace('@','')}" if (prof and prof.username and not str(prof.username).isdigit()) else "Sin @"
        u.user_level = prof.level if prof else 1
        u.user_rank = prof.get_rank_name(is_idol=(u.role == 'idol' or len(idols_map.get(u.telegram_id, [])) > 0)) if prof else "Curioso"
        u.has_bonus_cooldown = not w.can_claim_bonus() if w else False
        u.idol_names = idols_map.get(u.telegram_id, [])
        u.is_user_admin = (str(u.telegram_id) == ADMIN_TG_ID) or (u.role == 'admin')
        u.is_user_idol = (u.role == 'idol') or (len(u.idol_names) > 0)
        
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


@csrf_exempt
def telegram_webhook(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode('utf-8'))
            msg = data.get('message') or data.get('channel_post') or data.get('edited_message')
            
            if msg:
                text = (msg.get('text') or '').strip().lower()
                chat = msg.get('chat', {})
                chat_id = chat.get('id')
                user = msg.get('from', {})
                user_id = user.get('id')
                first_name = user.get('first_name', 'Noble')
                username = user.get('username')
                
                handle_real = f"@{username}" if username else first_name

                if user_id:
                    user_prof, _ = UserProfile.objects.get_or_create(telegram_user_id=user_id)
                    user_prof.username = handle_real
                    user_prof.save(update_fields=['username'])
                    IdolProfile.objects.filter(telegram_user_id=user_id).update(owner_username=handle_real)

                    if text.startswith(('/start', '/id', '/menu', '/app', 'entrar')):is_group = int(chat_id) < 0
                    if is_group:
                        # En grupos: enlace directo a abrir el bot en privado o la Mini App
                        app_link = "https://t.me/KingdomPleasure_bot?start=entrar"
                    else:
                        # En privado: Mini App con autenticación directa
                        app_link = f"https://kingdom-pleasure-app.onrender.com/?tg_id={user_id}&tg_username={encode_param(handle_real)}"
                    
                    if text.startswith('/id'):
                        texto = (
                            f"🆔 <b>Identificación Nobiliaria</b>\n\n"
                            f"👤 <b>Nombre:</b> {first_name}\n"
                            f"🏷️ <b>Usuario:</b> {handle_real}\n"
                            f"🔢 <b>Telegram ID:</b> <code>{user_id}</code>\n"
                            f"🏰 <b>Grupo ID:</b> <code>{chat_id}</code>"
                        )
                        btn_txt = "🌹 Abrir Mi Reino"
                    else:
                        texto = (
                            f"👑 <b>¡Saludos, {first_name}!</b>\n\n"
                            f"Las puertas de <b>Kingdom of Pleasure</b> están abiertas para los miembros de este círculo.\n\n"
                            f"Pulsa el botón dorado para cruzar el umbral con tu propia cuenta."
                        )
                        btn_txt = "✨ Entrar al Kingdom"
                    
                    # 👈 Ahora send_telegram_msg se ejecuta SIEMPRE (en grupos y en privado):
                    send_telegram_msg(
                        chat_id=chat_id, 
                        text=texto, 
                        button_text=btn_txt, 
                        button_url=app_link
                    )
        except Exception as e:
            print(f"⚠️ Error procesando webhook: {e}")

    return HttpResponse("OK")