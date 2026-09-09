from urllib.parse import quote as encode_param # <- Añade esto al inicio
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import IdolProfile, Review, Post, PostUnlock
from economy.models import Wallet  # Importamos la billetera para cobrar

def idol_list(request):
    tg_id = request.GET.get('tg_id')
    tg_username = request.GET.get('tg_username') # Recibimos el nombre actual
    
    idols = []
    if tg_id:
        idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
        
        # EL TRUCO: Si recibimos un nombre, actualizamos todas las fichas de este usuario de golpe
        if tg_username:
            idols.update(owner_username=tg_username)
            
    context = {
        'idols': idols,
        'can_add_more': len(idols) < 3,
        'tg_id': tg_id,
        'tg_username': tg_username # Lo pasamos al template
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
    posts = Post.objects.all().select_related('idol')
    
    # Lista de IDs de posts VIP que este usuario ya pagó
    unlocked_ids = []
    if tg_id:
        unlocked_ids = PostUnlock.objects.filter(
            client_telegram_id=tg_id
        ).values_list('post_id', flat=True)
        
    return render(request, 'idols/feed.html', {
        'posts': posts,
        'tg_id': tg_id,
        'unlocked_ids': list(unlocked_ids)
    })

def unlock_post(request, post_id):
    if request.method == 'POST':
        tg_id = request.POST.get('tg_id')
        post = get_object_or_404(Post, id=post_id)
        
        # Buscamos la bóveda del cliente
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        # Verificamos que sea de pago y tenga saldo
        if post.network == 'fans':
            if wallet.balance >= post.price:
                # 1. Le restamos el oro al cliente
                wallet.remove_funds(post.price)
                
                # 2. Registramos que ya desbloqueó esta foto
                PostUnlock.objects.get_or_create(post=post, client_telegram_id=tg_id)
                
                # (Opcional a futuro: Aquí podrías sumarle el oro al dueño de la Idol)
                
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