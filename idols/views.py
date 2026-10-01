from urllib.parse import quote as encode_param
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.http import JsonResponse
from django.contrib import messages

from .models import IdolProfile, Review, Post, PostUnlock, PostLike, CustomRequest, PostComment
from economy.models import Wallet
from core.models import UserProfile
from core.utils import grant_user_xp
from pets.models import Pet
from core.telegram_notify import send_telegram_msg


def resolve_safe_tg(request):
    raw_id = request.POST.get('tg_id') or request.GET.get('tg_id') or request.session.get('tg_id')
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
                    req_obj.client_telegram_id,
                    f"⚠️ <b>Petición de Antojo Rechazada</b>\n"
                    f"{req_obj.idol.stage_name} no pudo atender tu petición en este momento.\n"
                    f"Tus <b>{req_obj.bounty} 🪙 de oro</b> han sido devueltos a tu Bóveda."
                )
                messages.info(request, f"Petición rechazada. Se devolvieron los {req_obj.bounty} 🪙 al cliente.")
                
            elif action == 'accept_request':
                delivered_photo = request.FILES.get('delivered_photo')
                if not delivered_photo:
                    messages.error(request, "Debes adjuntar la foto del antojo para completar la entrega.")
                else:
                    req_obj.delivered_photo = delivered_photo
                    req_obj.status = 'accepted'
                    req_obj.save()
                    
                    idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
                    idol_wallet.add_funds(req_obj.bounty)
                    grant_user_xp(request, tg_id, 40, reason="Entrega de Antojo")
                    
                    send_telegram_msg(
                        req_obj.client_telegram_id,
                        f"🔥 <b>¡Tu Antojo ha sido entregado!</b>\n"
                        f"{req_obj.idol.stage_name} ha subido tu foto exclusiva solicitada.\n"
                        f"Ya puedes verla en tu Colección Privada."
                    )
                    messages.success(request, f"¡Antojo entregado con éxito! Recibiste +{req_obj.bounty} 🪙 en tu Bóveda (+40 EXP).")
                    
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
        messages.error(request, "Ya has alcanzado el límite máximo de 2 Idols consagradas.")
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
            grant_user_xp(request, tg_id, 50, reason="Creación de Idol")
            messages.success(request, f"✨ ¡{stage_name} ha sido consagrada en el Reino! (+50 EXP)")
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
        except Exception as e:
            messages.error(request, f"Error al registrar: {str(e)}")

    return render(request, 'idols/form.html', {'tg_id': tg_id, 'tg_username': tg_username})


def idol_edit(request, idol_id):
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id)
    
    if tg_id != idol.telegram_user_id and str(tg_id) != '7474444797':
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
        messages.success(request, f"¡Perfil de {idol.stage_name} actualizado con éxito!")
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
                messages.error(request, "Debes escribir un comentario sobre el servicio.")
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
                    grant_user_xp(request, tg_id, 25, reason="Reseña de Idol")
                    grant_user_xp(None, idol.telegram_user_id, 35 if rating_val == 5 else 20, reason="Calificación Recibida")
                    
                    send_telegram_msg(
                        idol.telegram_user_id,
                        f"⭐ <b>¡Nueva Reseña para {idol.stage_name}!</b>\n"
                        f"El noble <b>{tg_username}</b> te calificó con <b>{rating_val}★</b>:\n"
                        f"<i>«{comment_val}»</i>"
                    )
                    messages.success(request, "¡Tu reseña fue publicada con éxito (+25 EXP)!")
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
        'tg_username': tg_username
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
                
                grant_user_xp(request, tg_id, precio_final, reason="Desbloqueo VIP")
                grant_user_xp(None, post.idol.telegram_user_id, max(15, precio_final // 2), reason="Venta de Contenido VIP")

                send_telegram_msg(
                    post.idol.telegram_user_id,
                    f"💎 <b>¡Venta VIP en KingdomFans!</b>\n"
                    f"Un noble desbloqueó tu foto por <b>{precio_final} 🪙</b>.\n"
                    f"Has recibido <b>+{ganancia_idol} 🪙</b> netos ({int(tasa_idol*100)}%) y EXP en tu Bóveda."
                )
                
                desc_txt = " (con 15% de descuento por tu Víbora)" if (pet and pet.species == 'viper') else ""
                messages.success(request, f"¡Foto desbloqueada con éxito! (-{precio_final} 🪙{desc_txt} / +{precio_final} EXP)")
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
                messages.error(request, f"Tu rango actual de Musa solo permite fijar precios de hasta {max_price} 🪙 por foto.")
            else:
                Post.objects.create(
                    idol=idol,
                    network=network,
                    caption=caption,
                    image=image,
                    price=int(price) if network == 'fans' else 0
                )
                grant_user_xp(request, tg_id, 20, reason="Nuevo Post Publicado")
                messages.success(request, f"¡Post publicado exitosamente como {idol.stage_name}! (+20 EXP)")
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
    
    if tg_id:
        unlocked_posts = Post.objects.filter(
            unlocks__client_telegram_id=tg_id
        ).select_related('idol').order_by('-unlocks__unlocked_at')
        
    return render(request, 'idols/collection.html', {'tg_id': tg_id, 'posts': unlocked_posts})


def send_tip(request, post_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        post = get_object_or_404(Post, id=post_id)
        
        try:
            amount = int(request.POST.get('tip_amount', 0))
        except ValueError:
            amount = 0
            
        if amount <= 0:
            messages.error(request, "El monto de la propina debe ser mayor a 0.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        if tg_id and tg_id == post.idol.telegram_user_id:
            messages.info(request, "No puedes enviarte propinas a ti mismo.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if client_wallet.remove_funds(amount):
            comision = int(amount * 0.10)
            neto_idol = amount - comision
            
            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
            idol_wallet.add_funds(neto_idol)
            
            grant_user_xp(request, tg_id, amount, reason="Propina a Musa")
            grant_user_xp(None, post.idol.telegram_user_id, amount // 2, reason="Propina Recibida")

            send_telegram_msg(
                post.idol.telegram_user_id,
                f"🥂 <b>¡Te han invitado un trago!</b>\n"
                f"Un noble te obsequió <b>{amount} 🪙</b> en el Muro.\n"
                f"Has recibido <b>+{neto_idol} 🪙</b> directos a tu Bóveda y EXP de artista."
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

        # ✅ Mensaje detallado indicando a cuál de tus Idols se le pidió el antojo y con botón directo:
        send_telegram_msg(
            chat_id=idol.telegram_user_id,
            text=(
                f"📬 <b>¡Nueva Petición de Antojo para tu Musa {idol.stage_name}!</b> 🌹\n\n"
                f"👤 <b>Noble Solicitante:</b> {tg_username}\n"
                f"🪙 <b>Recompensa en custodia:</b> <b>+{bounty} 🪙</b>\n"
                f"📝 <b>Deseo:</b> <i>«{description}»</i>\n\n"
                f"Ingresa a tu panel de Idols para entregar la foto exclusiva o rechazarla."
            ),
            button_text=f"📸 Atender Antojo de {idol.stage_name}",
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
            messages.success(request, "Comentario publicado.")
            
        return redirect(f'/idols/feed/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')