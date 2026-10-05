import random
from urllib.parse import quote as encode_param
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.http import JsonResponse
from django.contrib import messages

from .models import (
    IdolProfile, Review, Post, PostUnlock, PostLike, 
    CustomRequest, PostComment, PhotocardBox, Photocard, UserPhotocard
)
from economy.models import Wallet
from core.models import UserProfile, UserRole
from core.utils import grant_user_xp
from pets.models import Pet
from core.telegram_notify import send_telegram_msg


def resolve_safe_tg(request):
    raw_id = (
        request.POST.get('tg_id') or 
        request.GET.get('tg_id') or 
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
    return None


def sync_user_profile(tg_id, username_raw):
    if not tg_id or not username_raw or str(username_raw).strip() in ['', 'None', 'undefined']:
        return None
    
    clean_username = str(username_raw).strip()
    if not clean_username.startswith('@') and not clean_username.startswith('Noble_'):
        clean_username = f"@{clean_username}"

    profile, _ = UserProfile.objects.get_or_create(
        telegram_user_id=tg_id,
        defaults={'username': clean_username}
    )
    if clean_username and profile.username != clean_username:
        profile.username = clean_username
        profile.save(update_fields=['username'])
    return profile


def idol_list(request):
    tg_id = resolve_safe_tg(request)
    tg_username = request.POST.get('tg_username') or request.GET.get('tg_username') or ''

    if not tg_id:
        return redirect('/')

    sync_user_profile(tg_id, tg_username)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            idol_id = request.POST.get('idol_id')
            new_status = request.POST.get('status')
            if idol_id and new_status:
                IdolProfile.objects.filter(id=idol_id, telegram_user_id=tg_id).update(status=new_status)
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
            
        elif action in ['accept_request', 'reject_request']:
            req_id = request.POST.get('request_id')
            req_obj = get_object_or_404(CustomRequest, id=req_id, idol__telegram_user_id=tg_id)
            
            if action == 'reject_request':
                client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=req_obj.client_telegram_id)
                client_wallet.add_funds(req_obj.bounty)
                req_obj.status = 'rejected'
                req_obj.save()
                
                send_telegram_msg(
                    chat_id=req_obj.client_telegram_id,
                    text=(
                        f"⚠️ <b>Petición Especial Rechazada</b>\n\n"
                        f"{req_obj.idol.stage_name} no pudo atender tu solicitud en este momento.\n"
                        f"Tus <b>{req_obj.bounty} 🪙 de oro</b> han sido devueltos a tu Bóveda."
                    ),
                    button_text="🪙 Revisar Mi Bóveda",
                    button_url=f"https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={req_obj.client_telegram_id}"
                )
                messages.info(request, f"Petición rechazada. Se devolvieron los {req_obj.bounty} 🪙 al cliente.")
                
            elif action == 'accept_request':
                delivered_photo = request.FILES.get('delivered_photo')
                if not delivered_photo:
                    messages.error(request, "Debes adjuntar la foto para completar la entrega.")
                else:
                    req_obj.delivered_photo = delivered_photo
                    req_obj.status = 'accepted'
                    req_obj.save()
                    
                    idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
                    idol_wallet.add_funds(req_obj.bounty)
                    grant_user_xp(request, tg_id, 25, reason="Entrega de Petición")
                    
                    send_telegram_msg(
                        chat_id=req_obj.client_telegram_id,
                        text=(
                            f"✨ <b>¡Tu Petición ha sido entregada!</b>\n\n"
                            f"🌹 <b>Musa:</b> {req_obj.idol.stage_name}\n"
                            f"📝 <b>Detalle:</b> <i>«{req_obj.description}»</i>\n\n"
                            f"La foto exclusiva ya se encuentra en tu Colección Privada."
                        ),
                        button_text="💎 Ver Mi Colección",
                        button_url=f"https://kingdom-pleasure-app.onrender.com/idols/collection/?tg_id={req_obj.client_telegram_id}"
                    )
                    messages.success(request, f"¡Petición entregada con éxito! Recibiste +{req_obj.bounty} 🪙 (+25 EXP).")
                    
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
    
    idols = list(IdolProfile.objects.filter(telegram_user_id=tg_id))
    pending_requests = CustomRequest.objects.filter(
        idol__telegram_user_id=tg_id,
        status='pending'
    ).select_related('idol')
            
    context = {
        'idols': idols,
        'can_add_more': len(idols) < 2,
        'tg_id': tg_id,
        'tg_username': tg_username,
        'pending_requests': pending_requests
    }
    return render(request, 'idols/list.html', context)


def idol_create(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
    tg_username = request.POST.get('tg_username') or request.GET.get('tg_username') or (profile.username if profile else f"@{tg_id}")
    
    if not tg_username.startswith('@'):
        tg_username = f"@{tg_username}"

    if IdolProfile.objects.filter(telegram_user_id=tg_id).count() >= 2:
        messages.error(request, "Ya has alcanzado el límite máximo de 2 Idols registradas.")
        return redirect(f'/idols/?tg_id={tg_id}')

    if request.method == 'POST':
        stage_name = request.POST.get('stage_name', '').strip()
        group = request.POST.get('group', '').strip()
        bio = request.POST.get('bio', '').strip()
        tagline = request.POST.get('tagline', '').strip()
        aura_color = request.POST.get('aura_color', 'purple')
        specialty = request.POST.get('specialty', '').strip()
        welcome_message = request.POST.get('welcome_message', '').strip()
        photo = request.FILES.get('photo')
        banner = request.FILES.get('banner')
        
        try:
            IdolProfile.objects.create(
                telegram_user_id=tg_id,
                owner_username=tg_username,
                stage_name=stage_name,
                group=group,
                bio=bio,
                tagline=tagline,
                aura_color=aura_color,
                specialty=specialty,
                welcome_message=welcome_message,
                photo=photo,
                banner=banner
            )
            grant_user_xp(request, tg_id, 30, reason="Creación de Idol")
            messages.success(request, f"✨ ¡{stage_name} ha sido registrada con éxito! (+30 EXP)")
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
        except Exception as e:
            messages.error(request, f"Error al registrar: {str(e)}")

    return render(request, 'idols/form.html', {'tg_id': tg_id, 'tg_username': tg_username})


def idol_edit(request, idol_id):
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id)
    
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(
        telegram_id=tg_id, role__in=['admin', 'moderador']
    ).exists()

    if tg_id != idol.telegram_user_id and not is_admin:
        messages.error(request, "No tienes permiso para editar esta Idol.")
        return redirect(f'/idols/?tg_id={tg_id}')
        
    if request.method == 'POST':
        idol.stage_name = request.POST.get('stage_name', idol.stage_name).strip()
        idol.group = request.POST.get('group', idol.group).strip()
        idol.bio = request.POST.get('bio', idol.bio).strip()
        idol.tagline = request.POST.get('tagline', idol.tagline).strip()
        idol.status = request.POST.get('status', idol.status)
        idol.aura_color = request.POST.get('aura_color', idol.aura_color)
        idol.specialty = request.POST.get('specialty', idol.specialty).strip()
        idol.welcome_message = request.POST.get('welcome_message', idol.welcome_message).strip()
        
        if 'photo' in request.FILES:
            idol.photo = request.FILES['photo']
        if 'banner' in request.FILES:
            idol.banner = request.FILES['banner']
            
        idol.save()
        messages.success(request, f"¡Perfil de {idol.stage_name} actualizado!")
        return redirect(f'/idols/{idol.id}/?tg_id={tg_id}')
        
    return render(request, 'idols/form.html', {'idol': idol, 'tg_id': tg_id})


def idol_delete(request, idol_id):
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id, telegram_user_id=tg_id)
    
    if request.method == 'POST':
        idol.delete()
        return redirect(f'/idols/?tg_id={tg_id}')
        
    return render(request, 'idols/confirm_delete.html', {'tg_id': tg_id, 'idol': idol})


def idol_gallery(request):
    tg_id = resolve_safe_tg(request)
    
    all_idols = IdolProfile.objects.annotate(
        total_unlocks=Count('posts__unlocks')
    ).order_by('-rating', '-total_unlocks')

    max_unlocks = max([i.total_unlocks for i in all_idols], default=0)

    for idol in all_idols:
        idol.is_trending = (max_unlocks > 0 and idol.total_unlocks == max_unlocks)
        idol.is_top_rated = (idol.rating >= 4.80 and idol.services_done >= 2)

    return render(request, 'idols/gallery.html', {
        'all_idols': all_idols,
        'tg_id': tg_id
    })


def idol_detail(request, idol_id):
    tg_id = resolve_safe_tg(request)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or (profile.username if profile else 'Noble')
    
    idol = get_object_or_404(IdolProfile, id=idol_id)
    reviews = idol.reviews.all()
    recent_posts = idol.posts.all().order_by('-created_at')[:6]
    
    unlocked_ids = []
    if tg_id:
        unlocked_ids = list(PostUnlock.objects.filter(
            client_telegram_id=tg_id,
            post__idol=idol
        ).values_list('post_id', flat=True))
        
        if tg_id == idol.telegram_user_id:
            unlocked_ids = list(recent_posts.values_list('id', flat=True))

    total_sales = PostUnlock.objects.filter(post__idol=idol).count()
    is_top_rated = (idol.rating >= 4.80 and idol.services_done >= 2)
    is_trending = (total_sales >= 3)
    
    if request.method == 'POST':
        try:
            rating_val = int(request.POST.get('rating', 5))
            comment_val = request.POST.get('comment', '').strip()
            
            if not comment_val:
                messages.error(request, "Debes escribir un comentario sobre la atención.")
            elif rating_val < 1 or rating_val > 5:
                messages.error(request, "La calificación debe ser entre 1 y 5 estrellas.")
            else:
                if tg_id and tg_id == idol.telegram_user_id:
                    messages.error(request, "No puedes calificar a tu propia Idol.")
                else:
                    Review.objects.create(
                        idol=idol,
                        client_telegram_id=tg_id if tg_id else 0,
                        client_username=tg_username,
                        rating=rating_val,
                        comment=comment_val
                    )
                    grant_user_xp(request, tg_id, 15, reason="Reseña de Idol")
                    grant_user_xp(None, idol.telegram_user_id, 20 if rating_val == 5 else 10, reason="Calificación Recibida")
                    
                    send_telegram_msg(
                        chat_id=idol.telegram_user_id,
                        text=(
                            f"⭐ <b>¡Nueva Reseña para {idol.stage_name}!</b>\n\n"
                            f"👤 <b>Usuario:</b> {tg_username}\n"
                            f"✨ <b>Puntuación:</b> {rating_val}★\n"
                            f"💬 <i>«{comment_val}»</i>"
                        ),
                        button_text=f"🌹 Ver Perfil de {idol.stage_name}",
                        button_url=f"https://kingdom-pleasure-app.onrender.com/idols/{idol.id}/?tg_id={idol.telegram_user_id}"
                    )
                    messages.success(request, "¡Tu reseña fue publicada con éxito (+15 EXP)!")
                    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
        except Exception as e:
            messages.error(request, f"Error al procesar reseña: {str(e)}")

    context = {
        'idol': idol,
        'reviews': reviews,
        'recent_posts': recent_posts,
        'unlocked_ids': unlocked_ids,
        'is_top_rated': is_top_rated,
        'is_trending': is_trending,
        'total_sales': total_sales,
        'tg_id': tg_id,
        'tg_username': tg_username,
    }
    return render(request, 'idols/detail.html', context)


def social_feed(request):
    tg_id = resolve_safe_tg(request)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    tg_username = request.GET.get('tg_username') or (profile.username if profile else 'Noble')
    
    posts = Post.objects.all().select_related('idol').prefetch_related('comments')
    unlocked_ids = []
    liked_ids = []
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(telegram_id=tg_id, role='admin').exists()
    
    if tg_id:
        pagados = list(PostUnlock.objects.filter(client_telegram_id=tg_id).values_list('post_id', flat=True))
        propios = list(Post.objects.filter(idol__telegram_user_id=tg_id).values_list('id', flat=True))
        unlocked_ids = set(pagados + propios)
        liked_ids = list(PostLike.objects.filter(client_telegram_id=tg_id).values_list('post_id', flat=True))
        
    return render(request, 'idols/feed.html', {
        'posts': posts,
        'tg_id': tg_id,
        'unlocked_ids': list(unlocked_ids),
        'liked_ids': liked_ids,
        'tg_username': tg_username,
        'is_admin': is_admin,
    })


def delete_post(request, post_id):
    tg_id = resolve_safe_tg(request)
    post = get_object_or_404(Post, id=post_id)
    
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(telegram_id=tg_id, role='admin').exists()
    is_owner = (tg_id == post.idol.telegram_user_id)

    if not (is_admin or is_owner):
        messages.error(request, "No tienes permiso para eliminar esta publicación.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    if request.method == 'POST':
        post.delete()
        messages.success(request, "🗑️ Publicación eliminada del Muro con éxito.")
        
    return redirect(f'/idols/feed/?tg_id={tg_id}')


def edit_post(request, post_id):
    tg_id = resolve_safe_tg(request)
    post = get_object_or_404(Post, id=post_id)
    
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(telegram_id=tg_id, role='admin').exists()
    is_owner = (tg_id == post.idol.telegram_user_id)

    if not (is_admin or is_owner):
        messages.error(request, "No tienes permiso para editar esta publicación.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    creator_profile = UserProfile.objects.filter(telegram_user_id=post.idol.telegram_user_id).first()
    max_price = creator_profile.max_post_price_allowed if creator_profile else 80

    if request.method == 'POST':
        post.caption = request.POST.get('caption', '').strip()
        network = request.POST.get('network', post.network)
        price = request.POST.get('price', post.price)

        if 'image' in request.FILES:
            post.image = request.FILES['image']

        post.network = network
        if network == 'fans':
            try:
                p_val = int(price)
                post.price = min(p_val, max_price) if not is_admin else p_val
            except ValueError:
                pass
        else:
            post.price = 0

        post.save()
        messages.success(request, "✨ Publicación actualizada con éxito.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    return render(request, 'idols/edit_post.html', {
        'post': post,
        'tg_id': tg_id,
        'max_price': max_price,
        'is_admin': is_admin
    })


def unlock_post(request, post_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        post = get_object_or_404(Post, id=post_id)
        
        if tg_id and tg_id == post.idol.telegram_user_id:
            messages.info(request, "Esta publicación es de tu Idol, ya la tienes desbloqueada.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
        
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if post.network == 'fans':
            pet = Pet.objects.filter(telegram_user_id=tg_id).first()
            precio_final = post.price
            if pet and pet.species == 'viper':
                precio_final = max(1, int(post.price * 0.85))

            if wallet.balance >= precio_final:
                wallet.remove_funds(precio_final)
                PostUnlock.objects.get_or_create(post=post, client_telegram_id=tg_id)
                
                idol_profile = UserProfile.objects.filter(telegram_user_id=post.idol.telegram_user_id).first()
                tasa_idol = idol_profile.idol_commission_rate if idol_profile else 0.85
                ganancia_idol = int(precio_final * tasa_idol)
                
                idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
                idol_wallet.add_funds(ganancia_idol)
                
                # EXP moderada y balanceada
                grant_user_xp(request, tg_id, max(5, precio_final // 4), reason="Desbloqueo VIP")
                grant_user_xp(None, post.idol.telegram_user_id, max(5, precio_final // 5), reason="Venta de Contenido VIP")

                client_prof = UserProfile.objects.filter(telegram_user_id=tg_id).first()
                comprador = client_prof.username if (client_prof and client_prof.username) else f"Noble_{tg_id}"
                
                send_telegram_msg(
                    chat_id=post.idol.telegram_user_id,
                    text=(
                        f"💎 <b>¡Venta VIP en KingdomFans!</b>\n\n"
                        f"🌹 <b>Musa:</b> {post.idol.stage_name}\n"
                        f"👤 <b>Comprador:</b> {comprador}\n"
                        f"🪙 <b>Precio:</b> {precio_final} 🪙\n"
                        f"💰 <b>Ganancia neta:</b> <b>+{ganancia_idol} 🪙</b> ({int(tasa_idol*100)}%)\n\n"
                        f"Tu oro ya se encuentra disponible en tu Bóveda."
                    ),
                    button_text="🪙 Ver Mi Bóveda",
                    button_url=f"https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={post.idol.telegram_user_id}"
                )
                
                desc_txt = " (con 15% de descuento por tu Víbora)" if (pet and pet.species == 'viper') else ""
                messages.success(request, f"¡Foto desbloqueada con éxito! (-{precio_final} 🪙{desc_txt})")
            else:
                messages.error(request, "No tienes suficiente oro en tu Bóveda.")
                
        return redirect(f'/idols/feed/?tg_id={tg_id}')


def create_post(request):
    tg_id = resolve_safe_tg(request)
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
    
    if not mis_idols.exists():
        messages.error(request, "Debes registrar al menos una Idol antes de publicar.")
        return redirect(f'/idols/?tg_id={tg_id}')
        
    creator_profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
    max_price = creator_profile.max_post_price_allowed if creator_profile else 80

    if request.method == 'POST':
        idol_id = request.POST.get('idol_id')
        network = request.POST.get('network')
        caption = request.POST.get('caption')
        image = request.FILES.get('image')
        price = request.POST.get('price', 50)

        if not price or str(price).strip() == '':
            price = 50
        
        try:
            idol = mis_idols.get(id=idol_id)
            if not image:
                messages.error(request, "Debes adjuntar una foto para el post.")
            elif network == 'fans' and int(price) > max_price:
                messages.error(request, f"Tu rango actual solo permite fijar precios de hasta {max_price} 🪙 por foto.")
            else:
                Post.objects.create(
                    idol=idol,
                    network=network,
                    caption=caption,
                    image=image,
                    price=int(price) if network == 'fans' else 0
                )
                grant_user_xp(request, tg_id, 15, reason="Nuevo Post Publicado")
                messages.success(request, f"¡Post publicado exitosamente como {idol.stage_name}! (+15 EXP)")
                return redirect(f'/idols/feed/?tg_id={tg_id}')
                
        except IdolProfile.DoesNotExist:
            messages.error(request, "Idol seleccionada inválida.")
        except ValueError:
            messages.error(request, "El precio ingresado no es válido.")
            
    return render(request, 'idols/create_post.html', {'tg_id': tg_id, 'mis_idols': mis_idols, 'max_price': max_price})


def toggle_like(request, post_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        if not tg_id:
            return JsonResponse({'error': 'No user ID provided'}, status=400)
            
        post = get_object_or_404(Post, id=post_id)
        existing_like = PostLike.objects.filter(post=post, client_telegram_id=tg_id).first()
        
        if existing_like:
            existing_like.delete()
            if post.likes > 0:
                post.likes -= 1
                post.save()
            liked = False
        else:
            PostLike.objects.create(post=post, client_telegram_id=tg_id)
            post.likes += 1
            post.save()
            liked = True
            
        return JsonResponse({'liked': liked, 'likes': post.likes})
        
    return JsonResponse({'error': 'Invalid method'}, status=405)


def my_collection(request):
    tg_id = resolve_safe_tg(request)
    unlocked_posts = []
    delivered_antojos = []
    
    if tg_id:
        unlocked_posts = Post.objects.filter(
            unlocks__client_telegram_id=tg_id
        ).select_related('idol').order_by('-unlocks__unlocked_at')
        
        delivered_antojos = CustomRequest.objects.filter(
            client_telegram_id=tg_id,
            status='accepted'
        ).exclude(delivered_photo='').select_related('idol').order_by('-created_at')
        
    return render(request, 'idols/collection.html', {
        'tg_id': tg_id, 
        'posts': unlocked_posts,
        'antojos': delivered_antojos,
        'total_items': len(unlocked_posts) + len(delivered_antojos)
    })


def send_tip(request, post_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        post = get_object_or_404(Post, id=post_id)
        
        try:
            amount = int(request.POST.get('tip_amount', 0))
        except ValueError:
            amount = 0
            
        if amount <= 0:
            messages.error(request, "El monto del brindis debe ser mayor a 0.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        if tg_id and tg_id == post.idol.telegram_user_id:
            messages.info(request, "No puedes enviarte ofrendas a ti mismo.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if client_wallet.remove_funds(amount):
            comision = int(amount * 0.10)
            neto_idol = amount - comision
            
            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
            idol_wallet.add_funds(neto_idol)
            
            # EXP calibrada
            grant_user_xp(request, tg_id, max(5, amount // 5), reason="Ofrenda a Musa")
            grant_user_xp(None, post.idol.telegram_user_id, max(5, amount // 5), reason="Ofrenda Recibida")

            client_prof = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            invitador = client_prof.username if (client_prof and client_prof.username) else f"Noble_{tg_id}"
            
            send_telegram_msg(
                chat_id=post.idol.telegram_user_id,
                text=(
                    f"🥂 <b>¡Te han invitado un trago Real!</b>\n\n"
                    f"🌹 <b>Para tu Musa:</b> {post.idol.stage_name}\n"
                    f"👤 <b>De parte de:</b> {invitador}\n"
                    f"🪙 <b>Ofrenda:</b> +{neto_idol} 🪙 netos directos a tu Bóveda."
                ),
                button_text="🥂 Ver Mi Bóveda",
                button_url=f"https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={post.idol.telegram_user_id}"
            )
            messages.success(request, f"🥂 ¡Le has invitado un trago de {amount} 🪙 a {post.idol.stage_name}!")
        else:
            messages.error(request, "No tienes suficiente oro en tu Bóveda.")
            
        return redirect(f'/idols/feed/?tg_id={tg_id}')


def create_custom_request(request, idol_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
        tg_username = request.POST.get('tg_username') or (profile.username if profile else 'Noble')
        idol = get_object_or_404(IdolProfile, id=idol_id)
        
        if tg_id and tg_id == idol.telegram_user_id:
            messages.error(request, "No puedes solicitarte una petición a ti misma.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

        try:
            bounty = int(request.POST.get('bounty', 100))
        except ValueError:
            bounty = 100
            
        description = request.POST.get('description', '').strip()
        if bounty <= 0 or not description:
            messages.error(request, "Por favor completa la descripción y una oferta válida.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
            
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        if not client_wallet.remove_funds(bounty):
            messages.error(request, f"No tienes suficiente oro ({bounty} 🪙) en tu Bóveda.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
            
        CustomRequest.objects.create(
            idol=idol,
            client_telegram_id=tg_id,
            client_username=tg_username,
            description=description,
            bounty=bounty,
            status='pending'
        )

        send_telegram_msg(
            chat_id=idol.telegram_user_id,
            text=(
                f"📬 <b>¡Nueva Petición Especial para tu Musa {idol.stage_name}!</b> 🌹\n\n"
                f"👤 <b>Solicitante:</b> {tg_username}\n"
                f"🪙 <b>Recompensa en custodia:</b> <b>+{bounty} 🪙</b>\n"
                f"📝 <b>Detalle:</b> <i>«{description}»</i>\n\n"
                f"Ingresa a tu panel de Idols para entregar la foto o rechazarla."
            ),
            button_text=f"📸 Atender Petición de {idol.stage_name}",
            button_url=f"https://kingdom-pleasure-app.onrender.com/idols/?tg_id={idol.telegram_user_id}"
        )
        messages.success(request, f"¡Petición enviada a {idol.stage_name}! Tu oro quedó en custodia.")
        
    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')


def add_comment(request, post_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
        tg_username = request.POST.get('tg_username') or (profile.username if profile else 'Noble')
        text = request.POST.get('text', '').strip()
        post = get_object_or_404(Post, id=post_id)
        
        if text:
            nombre_final = f"{post.idol.stage_name} (Idol)" if (tg_id and tg_id == post.idol.telegram_user_id) else tg_username
            PostComment.objects.create(
                post=post,
                author_telegram_id=tg_id if tg_id else 0,
                author_name=nombre_final,
                text=text
            )
            grant_user_xp(request, tg_id, 5, reason="Comentario en Muro")

            if tg_id != post.idol.telegram_user_id:
                send_telegram_msg(
                    chat_id=post.idol.telegram_user_id,
                    text=(
                        f"💬 <b>¡Nuevo comentario para tu Musa {post.idol.stage_name}!</b>\n\n"
                        f"👤 <b>Usuario:</b> {nombre_final}\n"
                        f"📝 <i>«{text}»</i>"
                    ),
                    button_text="📱 Ver Publicación",
                    button_url=f"https://kingdom-pleasure-app.onrender.com/idols/feed/?tg_id={post.idol.telegram_user_id}"
                )

            messages.success(request, "Comentario publicado (+5 EXP).")
            
        return redirect(f'/idols/feed/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')


# ==========================================
# SISTEMA DE PHOTOCARDS Y CAJAS CS
# ==========================================

def photocard_boxes_view(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    boxes = PhotocardBox.objects.filter(is_active=True).prefetch_related('cards')
    
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(
        telegram_id=tg_id, 
        role__in=['admin', 'moderador']
    ).exists()

    my_cards_count = UserPhotocard.objects.filter(telegram_user_id=tg_id).count()

    return render(request, 'idols/photocard_boxes.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'boxes': boxes,
        'is_admin': is_admin,
        'my_cards_count': my_cards_count,
    })


def open_photocard_box_ajax(request, box_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return JsonResponse({'success': False, 'error': 'Sesión no identificada'}, status=400)

    box = get_object_or_404(PhotocardBox, id=box_id, is_active=True)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    if wallet.balance < box.price:
        return JsonResponse({'success': False, 'error': f'No tienes suficiente oro ({box.price} 🪙 necesarios).'}, status=400)

    all_cards = list(box.cards.all())
    if not all_cards:
        return JsonResponse({'success': False, 'error': 'Esta caja aún no tiene cartas cargadas.'}, status=400)

    wallet.remove_funds(box.price)

    # Probabilidades de Counter-Strike
    roll = random.random() * 100
    if roll < 3.0:
        target_rarity = 'legendary'
    elif roll < 15.0:
        target_rarity = 'epic'
    elif roll < 40.0:
        target_rarity = 'rare'
    else:
        target_rarity = 'common'

    pool = [c for c in all_cards if c.rarity == target_rarity]
    winner = random.choice(pool) if pool else random.choice(all_cards)

    UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=winner)

    # EXP balanceada (sin inflación)
    xp_map = {'common': 5, 'rare': 12, 'epic': 25, 'legendary': 50}
    grant_user_xp(request, tg_id, xp_map.get(winner.rarity, 10), reason=f"Photocard {winner.get_rarity_display()}")

    reel = []
    for i in range(35):
        card_item = winner if i == 28 else random.choice(all_cards)
        reel.append({
            'id': card_item.id,
            'name': card_item.name,
            'rarity': card_item.rarity,
            'rarity_display': card_item.get_rarity_display(),
            'color': card_item.get_color_hex(),
            'image_url': card_item.image.url if card_item.image else '',
            'idol_name': card_item.display_idol_name,
        })

    return JsonResponse({
        'success': True,
        'nuevo_saldo': wallet.balance,
        'winning_index': 28,
        'winner': {
            'id': winner.id,
            'name': winner.name,
            'rarity': winner.rarity,
            'rarity_display': winner.get_rarity_display(),
            'color': winner.get_color_hex(),
            'image_url': winner.image.url if winner.image else '',
            'idol_name': winner.display_idol_name,
        },
        'reel': reel
    })


def my_photocards_album(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    user_cards = UserPhotocard.objects.filter(
        telegram_user_id=tg_id
    ).select_related('photocard', 'photocard__idol', 'photocard__box').order_by('-obtained_at')

    total = user_cards.count()
    legendaries = user_cards.filter(photocard__rarity='legendary').count()
    epics = user_cards.filter(photocard__rarity='epic').count()

    return render(request, 'idols/photocards_album.html', {
        'tg_id': tg_id,
        'user_cards': user_cards,
        'total': total,
        'legendaries': legendaries,
        'epics': epics,
    })


def admin_photocards_manage(request):
    tg_id = resolve_safe_tg(request)
    is_admin = (str(tg_id) == '7474444797') or UserRole.objects.filter(
        telegram_id=tg_id, 
        role__in=['admin', 'moderador']
    ).exists()

    if not is_admin:
        messages.error(request, "Solo los administradores pueden gestionar Photocards.")
        return redirect('/idols/photocards/')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_box':
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            price = int(request.POST.get('price', 50))
            cover_image = request.FILES.get('cover_image')
            if name:
                PhotocardBox.objects.create(name=name, description=description, price=price, cover_image=cover_image)
                messages.success(request, f"✨ Caja «{name}» creada.")

        elif action == 'edit_box':
            box_id = request.POST.get('box_id')
            box = get_object_or_404(PhotocardBox, id=box_id)
            box.name = request.POST.get('name', box.name).strip()
            box.description = request.POST.get('description', box.description).strip()
            box.price = int(request.POST.get('price', box.price))
            if 'cover_image' in request.FILES:
                box.cover_image = request.FILES['cover_image']
            box.save()
            messages.success(request, f"💾 Caja «{box.name}» actualizada.")

        elif action == 'delete_box':
            box_id = request.POST.get('box_id')
            box = get_object_or_404(PhotocardBox, id=box_id)
            box_name = box.name
            box.delete()
            messages.warning(request, f"🗑️ Caja «{box_name}» eliminada.")

        elif action == 'toggle_box':
            box_id = request.POST.get('box_id')
            box = get_object_or_404(PhotocardBox, id=box_id)
            box.is_active = not box.is_active
            box.save()
            estado = "Activada" if box.is_active else "Pausada"
            messages.info(request, f"Caja {box.name} {estado}.")

        elif action == 'upload_card':
            box_id = request.POST.get('box_id')
            idol_name = request.POST.get('idol_name', '').strip()
            name = request.POST.get('name', '').strip()
            rarity = request.POST.get('rarity', 'common')
            image = request.FILES.get('image')

            if not image or not name or not box_id:
                messages.error(request, "Debes adjuntar el archivo de Canva, asignar un nombre y una caja.")
            else:
                box_obj = get_object_or_404(PhotocardBox, id=box_id)
                Photocard.objects.create(
                    box=box_obj,
                    idol_name=idol_name or "K-Pop Idol",
                    name=name,
                    rarity=rarity,
                    image=image,
                    created_by_tg_id=tg_id
                )
                messages.success(request, f"🎴 Photocard «{name}» ({idol_name}) subida con éxito.")

        elif action == 'edit_card':
            card_id = request.POST.get('card_id')
            card = get_object_or_404(Photocard, id=card_id)
            card.box_id = request.POST.get('box_id', card.box_id)
            card.idol_name = request.POST.get('idol_name', card.idol_name).strip()
            card.name = request.POST.get('name', card.name).strip()
            card.rarity = request.POST.get('rarity', card.rarity)
            if 'image' in request.FILES:
                card.image = request.FILES['image']
            card.save()
            messages.success(request, f"💾 Photocard «{card.name}» actualizada.")

        elif action == 'delete_card':
            card_id = request.POST.get('card_id')
            card = get_object_or_404(Photocard, id=card_id)
            c_name = card.name
            card.delete()
            messages.warning(request, f"🗑️ Photocard «{c_name}» eliminada.")

        return redirect(f'/idols/photocards/admin/?tg_id={tg_id}')

    boxes = PhotocardBox.objects.all().prefetch_related('cards')
    all_idols = IdolProfile.objects.all().order_by('stage_name')
    all_cards = Photocard.objects.all().select_related('box').order_by('-created_at')

    return render(request, 'idols/admin_photocards.html', {
        'tg_id': tg_id,
        'boxes': boxes,
        'all_idols': all_idols,
        'all_cards': all_cards,
    })