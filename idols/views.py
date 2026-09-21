from urllib.parse import quote as encode_param # <- Añade esto al inicio
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from .models import IdolProfile, Review, Post, PostUnlock, PostLike, CustomRequest, PostComment
from economy.models import Wallet  # Importamos la billetera para cobrar

def idol_list(request):
    tg_id = request.GET.get('tg_id')
    tg_username = request.GET.get('tg_username')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. Actualizar estado
        if action == 'update_status':
            idol_id = request.POST.get('idol_id')
            new_status = request.POST.get('status')
            if idol_id and new_status and tg_id:
                IdolProfile.objects.filter(id=idol_id, telegram_user_id=tg_id).update(status=new_status)
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username or "")}')
            
        # 2. Responder Petición de Antojo
        elif action in ['accept_request', 'reject_request']:
            req_id = request.POST.get('request_id')
            req_obj = get_object_or_404(CustomRequest, id=req_id, idol__telegram_user_id=tg_id)
            
            if action == 'reject_request':
                # Devolvemos el oro en garantía al cliente
                client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=req_obj.client_telegram_id)
                client_wallet.add_funds(req_obj.bounty)
                req_obj.status = 'rejected'
                req_obj.save()
                messages.info(request, f"Petición rechazada. Se devolvieron los {req_obj.bounty} 🪙 al cliente.")
                
            elif action == 'accept_request':
                delivered_photo = request.FILES.get('delivered_photo')
                if not delivered_photo:
                    messages.error(request, "Debes adjuntar la foto del antojo para completar la entrega.")
                else:
                    req_obj.delivered_photo = delivered_photo
                    req_obj.status = 'accepted'
                    req_obj.save()
                    
                    # Pagamos el oro a la Bóveda de la Idol
                    idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
                    idol_wallet.add_funds(req_obj.bounty)
                    messages.success(request, f"¡Antojo entregado con éxito! Recibiste +{req_obj.bounty} 🪙 en tu Bóveda.")
                    
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username or "")}')
    
    idols = []
    pending_requests = []
    if tg_id:
        idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
        if tg_username:
            idols.update(owner_username=tg_username)
        # Peticiones pendientes para las Idols de esta Roller
        pending_requests = CustomRequest.objects.filter(
            idol__telegram_user_id=tg_id,
            status='pending'
        ).select_related('idol')
            
    context = {
        'idols': idols,
        'can_add_more': len(idols) < 3,
        'tg_id': tg_id,
        'tg_username': tg_username,
        'pending_requests': pending_requests
    }
    return render(request, 'idols/list.html', context)

def idol_create(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username')
    
    if request.method == 'POST':
        stage_name = request.POST.get('stage_name')
        group = request.POST.get('group')
        bio = request.POST.get('bio')
        photo = request.FILES.get('photo')
        
        try:
            IdolProfile.objects.create(
                telegram_user_id=tg_id,
                owner_username=tg_username, # Guardamos el nombre al crear
                stage_name=stage_name,
                group=group,
                bio=bio,
                photo=photo
            )
            return redirect(f'/idols/?tg_id={tg_id}&tg_username={tg_username}')
        except Exception as e:
            messages.error(request, str(e))

    return render(request, 'idols/form.html', {'tg_id': tg_id, 'tg_username': tg_username})

# --- NUEVAS FUNCIONES ---

def idol_edit(request, idol_id):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    # Seguridad vital: Buscamos la idol, pero exigimos que pertenezca al tg_id actual
    idol = get_object_or_404(IdolProfile, id=idol_id, telegram_user_id=tg_id)
    
    if request.method == 'POST':
        idol.stage_name = request.POST.get('stage_name')
        idol.group = request.POST.get('group')
        idol.bio = request.POST.get('bio')
        
        # Solo actualizamos la foto si subieron una nueva
        if 'photo' in request.FILES:
            idol.photo = request.FILES.get('photo')
            
        idol.save()
        return redirect(f'/idols/?tg_id={tg_id}')
        
    # Reutilizamos form.html, pero le enviamos la "idol" para que llene los campos
    return render(request, 'idols/form.html', {'tg_id': tg_id, 'idol': idol})

def idol_delete(request, idol_id):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    idol = get_object_or_404(IdolProfile, id=idol_id, telegram_user_id=tg_id)
    
    if request.method == 'POST':
        idol.delete()
        return redirect(f'/idols/?tg_id={tg_id}')
        
    return render(request, 'idols/confirm_delete.html', {'tg_id': tg_id, 'idol': idol})

def idol_gallery(request):
    all_idols = IdolProfile.objects.all().order_by('stage_name')
    print("Idols en la base de datos:", all_idols.count()) # <- Añade esto
    return render(request, 'idols/gallery.html', {'all_idols': all_idols})

def idol_detail(request, idol_id):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or 'Cliente VIP'
    
    idol = get_object_or_404(IdolProfile, id=idol_id)
    reviews = idol.reviews.all()
    
    if request.method == 'POST':
        try:
            rating_val = int(request.POST.get('rating', 5))
            comment_val = request.POST.get('comment', '').strip()
            
            if not comment_val:
                messages.error(request, "Debes escribir un comentario sobre el servicio.")
            elif rating_val < 1 or rating_val > 5:
                messages.error(request, "La calificación debe ser entre 1 y 5 estrellas.")
            else:
                if tg_id and int(tg_id) == idol.telegram_user_id:
                    messages.error(request, "No puedes calificar a tu propia Idol.")
                else:
                    Review.objects.create(
                        idol=idol,
                        client_telegram_id=tg_id if tg_id else 0,
                        client_username=tg_username,
                        rating=rating_val,
                        comment=comment_val
                    )
                    messages.success(request, "¡Tu reseña fue publicada con éxito!")
                    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
        except Exception as e:
            messages.error(request, f"Error al procesar reseña: {str(e)}")

    context = {
        'idol': idol,
        'reviews': reviews,
        'tg_id': tg_id,
        'tg_username': tg_username,
    }
    return render(request, 'idols/detail.html', context)

def social_feed(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    
    # Traemos todos los posts, del más nuevo al más viejo
    posts = Post.objects.all().select_related('idol').prefetch_related('comments')
    
    # Lista de IDs de posts VIP que este usuario ya pagó o que son de sus propias Idols
    unlocked_ids = []
    if tg_id:
        # Posts pagados por el cliente
        pagados = list(PostUnlock.objects.filter(
            client_telegram_id=tg_id
        ).values_list('post_id', flat=True))
        
        # Posts que le pertenecen a las Idols del usuario actual (gratis para el creador)
        propios = list(Post.objects.filter(
            idol__telegram_user_id=tg_id
        ).values_list('id', flat=True))
        
        unlocked_ids = set(pagados + propios)
    
    # IDs de posts a los que este usuario ya dio like
    
        liked_ids = list(PostLike.objects.filter(
            client_telegram_id=tg_id
        ).values_list('post_id', flat=True))

        tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or 'Ciudadano VIP'
        
    return render(request, 'idols/feed.html', {
        'posts': posts,
        'tg_id': tg_id,
        'unlocked_ids': list(unlocked_ids),
        'liked_ids': liked_ids,  # <- AGREGAR ESTA LÍNEA
        'tg_username': tg_username
    })

def unlock_post(request, post_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        post = get_object_or_404(Post, id=post_id)
        
        # Validación: si es el dueño de la Idol, no se cobra
        if tg_id and int(tg_id) == post.idol.telegram_user_id:
            messages.info(request, "Esta publicación es de tu Idol, ya la tienes desbloqueada.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
        
        # Buscamos la bóveda del cliente
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        # Verificamos que sea de pago y tenga saldo
        if post.network == 'fans':
            if wallet.balance >= post.price:
                # 1. Descontamos el oro al cliente
                wallet.remove_funds(post.price)
                
                # 2. Registramos que el cliente desbloqueó la foto
                PostUnlock.objects.get_or_create(post=post, client_telegram_id=tg_id)
                
                # 3. 💰 TRANSFERENCIA DE ORO A LA IDOL:
                idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
                idol_wallet.add_funds(post.price)
                
                messages.success(request, f"¡Foto desbloqueada con éxito! (-{post.price} 🪙)")
            else:
                messages.error(request, "No tienes suficiente oro en tu Bóveda.")
                
        return redirect(f'/idols/feed/?tg_id={tg_id}')
    
def create_post(request):
    tg_id = request.GET.get('tg_id') or request.POST.get('tg_id')
    
    # Buscamos SOLO las Idols que le pertenecen a este Roller
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
    
    # Si no tiene Idols, no puede publicar
    if not mis_idols.exists():
        messages.error(request, "Debes registrar al menos una Idol antes de publicar.")
        return redirect(f'/idols/?tg_id={tg_id}')
        
    if request.method == 'POST':
        idol_id = request.POST.get('idol_id')
        network = request.POST.get('network')
        caption = request.POST.get('caption')
        image = request.FILES.get('image') # OJO: request.FILES para las imágenes
        price = request.POST.get('price', 0)
        
        try:
            # Verificamos por seguridad que la Idol seleccionada realmente sea suya
            idol = mis_idols.get(id=idol_id)
            
            if not image:
                messages.error(request, "Debes adjuntar una foto para el post.")
            else:
                # Creamos el Post en la base de datos
                Post.objects.create(
                    idol=idol,
                    network=network,
                    caption=caption,
                    image=image,
                    price=int(price) if network == 'fans' else 0
                )
                messages.success(request, f"¡Post publicado exitosamente como {idol.stage_name}!")
                return redirect(f'/idols/feed/?tg_id={tg_id}')
                
        except IdolProfile.DoesNotExist:
            messages.error(request, "Idol seleccionada inválida.")
        except ValueError:
            messages.error(request, "El precio ingresado no es válido.")
            
    return render(request, 'idols/create_post.html', {
        'tg_id': tg_id,
        'mis_idols': mis_idols
    })
    
def toggle_like(request, post_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        if not tg_id:
            return JsonResponse({'error': 'No user ID provided'}, status=400)
            
        post = get_object_or_404(Post, id=post_id)
        
        # Verificamos si ya dio like
        existing_like = PostLike.objects.filter(post=post, client_telegram_id=tg_id).first()
        
        if existing_like:
            # Si ya existía, lo quitamos
            existing_like.delete()
            if post.likes > 0:
                post.likes -= 1
                post.save()
            liked = False
        else:
            # Si no existía, lo creamos
            PostLike.objects.create(post=post, client_telegram_id=tg_id)
            post.likes += 1
            post.save()
            liked = True
            
        return JsonResponse({'liked': liked, 'likes': post.likes})
        
    return JsonResponse({'error': 'Invalid method'}, status=405)

def my_collection(request):
    tg_id = request.GET.get('tg_id') or request.session.get('tg_id')
    unlocked_posts = []
    
    if tg_id:
        # Buscamos todos los registros de PostUnlock del usuario con sus posts e idols
        unlocked_posts = Post.objects.filter(
            unlocks__client_telegram_id=tg_id
        ).select_related('idol').order_by('-unlocks__unlocked_at')
        
    return render(request, 'idols/collection.html', {
        'tg_id': tg_id,
        'posts': unlocked_posts
    })

def send_tip(request, post_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        post = get_object_or_404(Post, id=post_id)
        
        try:
            amount = int(request.POST.get('tip_amount', 0))
        except ValueError:
            amount = 0
            
        if amount <= 0:
            messages.error(request, "El monto de la propina debe ser mayor a 0.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        # Validación: No puedes darte propina a tu propia Idol
        if tg_id and int(tg_id) == post.idol.telegram_user_id:
            messages.info(request, "No puedes enviarte propinas a ti mismo.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        # Buscar la billetera del cliente
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if client_wallet.remove_funds(amount):
            # Transferir el oro a la Idol
            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
            idol_wallet.add_funds(amount)
            messages.success(request, f"🥂 ¡Le has invitado un trago de {amount} 🪙 a {post.idol.stage_name}!")
        else:
            messages.error(request, "No tienes suficiente oro en tu Bóveda.")
            
        return redirect(f'/idols/feed/?tg_id={tg_id}')

def create_custom_request(request, idol_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        tg_username = request.POST.get('tg_username') or 'Cliente VIP'
        idol = get_object_or_404(IdolProfile, id=idol_id)
        
        try:
            bounty = int(request.POST.get('bounty', 100))
        except ValueError:
            bounty = 100
            
        description = request.POST.get('description', '').strip()
        
        if bounty <= 0 or not description:
            messages.error(request, "Por favor completa la descripción y una oferta válida.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
            
        # Comprobar si el cliente tiene saldo suficiente
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        if not client_wallet.remove_funds(bounty):
            messages.error(request, f"No tienes suficiente oro ({bounty} 🪙) en tu Bóveda.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
            
        # Crear la petición reteniendo el oro
        CustomRequest.objects.create(
            idol=idol,
            client_telegram_id=tg_id,
            client_username=tg_username,
            description=description,
            bounty=bounty,
            status='pending'
        )
        messages.success(request, f"¡Petición enviada a {idol.stage_name}! Tu oro ({bounty} 🪙) quedó en custodia hasta que sea aceptada.")
        
    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

def add_comment(request, post_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        tg_username = request.POST.get('tg_username') or 'Cliente VIP'
        text = request.POST.get('text', '').strip()
        
        post = get_object_or_404(Post, id=post_id)
        
        if text:
            # Si el que comenta es el dueño de la Idol, guardamos el nombre con corona
            if tg_id and int(tg_id) == post.idol.telegram_user_id:
                nombre_final = f"{post.idol.stage_name} (Idol)"
            else:
                nombre_final = tg_username
                
            PostComment.objects.create(
                post=post,
                author_telegram_id=tg_id if tg_id else 0,
                author_name=nombre_final,
                text=text
            )
            messages.success(request, "Comentario publicado.")
            
        return redirect(f'/idols/feed/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')