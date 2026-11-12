

import random
import os
import sys
import uuid
import urllib.request
from io import BytesIO
from PIL import Image
from urllib.parse import quote as encode_param
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q, Avg
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.text import slugify

from .models import (
    IdolProfile, Review, Post, PostImage, PostUnlock, PostLike, 
    CustomRequest, PostComment, PhotocardBox, Photocard, UserPhotocard, PhotocardTrade, RoleSessionRequest
)
from economy.models import Wallet
from core.models import UserProfile, UserRole, KingdomSetting
from core.utils import grant_user_xp
from pets.models import Pet
from core.telegram_notify import send_telegram_msg
from collections import Counter


ADMIN_CORONA_ID = '7474444797'


def check_is_staff_or_admin(tg_id):
    if not tg_id:
        return False
    if str(tg_id) == ADMIN_CORONA_ID:
        return True
    role_obj = UserRole.objects.filter(telegram_id=tg_id).first()
    if not role_obj:
        return False
    staff = getattr(role_obj, 'staff_role', 'none')
    return (staff in ['admin', 'moderador']) or (role_obj.role in ['admin', 'moderador']) or getattr(role_obj, 'is_moderator', False)


def download_image_from_url(url, default_filename='downloaded_image.webp'):
    """Descarga una imagen desde enlace web con User-Agent seguro y la retorna como buffer para Django"""
    if not url or not str(url).strip().startswith(('http://', 'https://')):
        return None
    try:
        req = urllib.request.Request(
            url.strip(),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            if len(data) > 12 * 1024 * 1024:
                return None
            bio = BytesIO(data)
            bio.name = default_filename
            return bio
    except Exception as e:
        print(f"Error descargando imagen desde URL {url}: {e}")
        return None


def optimize_uploaded_image(file_obj, max_dimension=1080, quality=78):
    if not file_obj:
        return file_obj
    try:
        img = Image.open(file_obj)

        # Corregir rotación automática de celular
        try:
            from PIL import ExifTags
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break
            exif = img._getexif()
            if exif and orientation in exif:
                if exif[orientation] == 3: img = img.rotate(180, expand=True)
                elif exif[orientation] == 6: img = img.rotate(270, expand=True)
                elif exif[orientation] == 8: img = img.rotate(90, expand=True)
        except Exception:
            pass

        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        output = BytesIO()
        has_alpha = img.mode in ('RGBA', 'LA') or ('transparency' in img.info)
        if has_alpha:
            img.save(output, format='WEBP', quality=quality, method=4)
        else:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output, format='WEBP', quality=quality, method=4)

        output.seek(0)
        # 🛡️ BLINDAJE ANTI-VARCHAR(100): Nombre ultracorto aleatorio (ej: musa_a1b2c3d4.webp)
        filename = f"musa_{uuid.uuid4().hex[:10]}.webp"

        return InMemoryUploadedFile(
            output, 'ImageField', filename, 'image/webp', output.getbuffer().nbytes, None
        )
    except Exception as e:
        print(f"Error optimizando imagen: {e}")
        return file_obj


def resolve_safe_tg(request):
    raw_id = request.GET.get('tg_id') or request.POST.get('tg_id') or request.session.get('tg_id')
    if raw_id and str(raw_id).strip() not in ['', 'None', 'undefined', 'null']:
        try:
            val = int(raw_id)
            request.session['tg_id'] = val
            return val
        except ValueError:
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

    UserRole.objects.get_or_create(telegram_id=tg_id, defaults={'role': 'idol', 'staff_role': 'none'})

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            idol_id = request.POST.get('idol_id')
            new_status = request.POST.get('status')
            if idol_id and new_status:
                idol = IdolProfile.objects.filter(id=idol_id, telegram_user_id=tg_id).first()
                if idol and idol.status != new_status:
                    idol.status = new_status
                    idol.save(update_fields=['status'])

                    group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)
                    if group_id and new_status in ['online', 'antojos']:
                        if new_status == 'online':
                            status_text = (
                                f"🟢 <b>¡Musa en los Aposentos Reales!</b> ✨\n\n"
                                f"🌹 <b>{idol.stage_name}</b> se encuentra disponible para chatear y atender a los nobles de la corte.\n\n"
                                f"¿Deseas iniciar una conversación privada?"
                            )
                            btn_text = f"💬 Hablar con {idol.stage_name}"
                        else:
                            status_text = (
                                f"🔥 <b>¡Sesión de Antojos Abierta!</b> 🔞\n\n"
                                f"🌹 <b>{idol.stage_name}</b> acaba de abrir su bandeja para peticiones especiales y fotos a pedido.\n\n"
                                f"¡Haz tu solicitud antes de que se agoten los cupos!"
                            )
                            btn_text = f"💌 Pedir Antojo a {idol.stage_name}"

                        send_telegram_msg(
                            chat_id=group_id,
                            text=status_text,
                            button_text=btn_text,
                            button_url="https://t.me/KingdomPleasure_bot?start=entrar"
                        )

            return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
            
        elif action in ['accept_request', 'reject_request']:
            req_id = request.POST.get('request_id')
            with transaction.atomic():
                req_obj = CustomRequest.objects.select_for_update().filter(id=req_id, idol__telegram_user_id=tg_id).first()
                if not req_obj:
                    messages.error(request, 'Petición no encontrada o no pertenece a tu perfil.')
                    return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
                
                if req_obj.status != 'pending':
                    messages.warning(request, f'Esta petición ya se encuentra {req_obj.get_status_display().lower()}.')
                    return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
                
                if action == 'reject_request':
                    client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=req_obj.client_telegram_id)
                    client_wallet.add_funds(req_obj.bounty)
                    req_obj.status = 'rejected'
                    req_obj.save()
                    
                    try:
                        reject_text = (
                            f'⚠️ <b>Petición Especial Rechazada</b>\n\n'
                            f'{req_obj.idol.stage_name} no pudo atender tu solicitud en este momento.\n'
                            f'Tus <b>{req_obj.bounty} 🪙 de oro</b> han sido devueltos a tu Bóveda.'
                        )
                        send_telegram_msg(
                            chat_id=req_obj.client_telegram_id,
                            text=reject_text,
                            button_text='🪙 Revisar Mi Bóveda',
                            button_url=f'https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={req_obj.client_telegram_id}'
                        )
                    except Exception as te:
                        print(f'Error enviando telegram de rechazo: {te}')
                        
                    messages.info(request, f'Petición rechazada. Se devolvieron los {req_obj.bounty} 🪙 al noble.')
                    return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
                
                elif action == 'accept_request':
                    delivered_media = request.FILES.get('delivered_photo')
                    if not delivered_media:
                        messages.error(request, 'Debes adjuntar la foto o video exclusivo para completar la entrega.')
                        return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
                    
                    # Límite de seguridad: 30 MB
                    if delivered_media.size > 30 * 1024 * 1024:
                        messages.error(request, 'El archivo adjunto supera el límite máximo permitido de 30 MB.')
                        return redirect(f'/idols/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
                    
                    file_name = delivered_media.name.lower()
                    is_video_upload = any(file_name.endswith(ext) for ext in ['.mp4', '.mov', '.webm', '.m4v', '.avi']) or 'video' in getattr(delivered_media, 'content_type', '')
                    
                    if is_video_upload:
                        ext = os.path.splitext(delivered_media.name)[1].lower() or '.mp4'
                        delivered_media.name = f"antojo_{uuid.uuid4().hex[:10]}{ext}"
                        req_obj.delivered_photo = delivered_media
                    else:
                        try:
                            req_obj.delivered_photo = optimize_uploaded_image(delivered_media)
                        except Exception as e:
                            print(f'Fallo optimización imagen: {e}')
                            req_obj.delivered_photo = delivered_media
                    
                    delivery_note = request.POST.get('delivery_note', '').strip()
                    if delivery_note:
                        req_obj.delivery_note = delivery_note[:250]
                    
                    req_obj.status = 'accepted'
                    req_obj.save()
                    
                    idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
                    idol_wallet.add_funds(req_obj.bounty)
                    grant_user_xp(request, tg_id, 25, reason='Entrega de Petición')
                    
                    try:
                        media_label = '🎬 El video exclusivo' if req_obj.is_video else '📸 La foto exclusiva'
                        note_line = f'\n💬 <b>Dedicatoria:</b> <i>«{req_obj.delivery_note}»</i>' if req_obj.delivery_note else ''
                        accept_text = (
                            f'✨ <b>¡Tu Petición ha sido entregada!</b>\n\n'
                            f'🌹 <b>Musa:</b> {req_obj.idol.stage_name}\n'
                            f'📝 <b>Detalle:</b> <i>«{req_obj.description}»</i>'
                            f'{note_line}\n\n'
                            f'{media_label} ya se encuentra en tu Colección Privada.'
                        )
                        send_telegram_msg(
                            chat_id=req_obj.client_telegram_id,
                            text=accept_text,
                            button_text='💎 Ver Mi Colección',
                            button_url=f'https://kingdom-pleasure-app.onrender.com/idols/collection/?tg_id={req_obj.client_telegram_id}'
                        )
                    except Exception as te:
                        print(f'Error enviando telegram de entrega: {te}')
                        
                    messages.success(request, f'¡Petición entregada con éxito! Recibiste +{req_obj.bounty} 🪙 (+25 EXP).')
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
        status = request.POST.get('status', 'online')
        aura_color = request.POST.get('aura_color', 'purple')
        specialty = request.POST.get('specialty', '').strip()
        welcome_message = request.POST.get('welcome_message', '').strip()
        custom_owner = request.POST.get('owner_username', tg_username).strip()
        if custom_owner and not custom_owner.startswith('@'):
            custom_owner = f"@{custom_owner}"

        # Procesar Retrato (Archivo nativo o URL de rescate para PC/Celular)
        photo_file = request.FILES.get('photo')
        photo_url = request.POST.get('photo_url', '').strip()
        if not photo_file and photo_url:
            photo_file = download_image_from_url(photo_url, default_filename=f"idol_{slugify(stage_name or 'photo')}.webp")
        photo = optimize_uploaded_image(photo_file)

        # Procesar Banner (Archivo nativo o URL de rescate)
        banner_file = request.FILES.get('banner')
        banner_url = request.POST.get('banner_url', '').strip()
        if not banner_file and banner_url:
            banner_file = download_image_from_url(banner_url, default_filename=f"banner_{slugify(stage_name or 'banner')}.webp")
        banner = optimize_uploaded_image(banner_file)

        if not photo:
            messages.error(request, "⚠️ Debes elegir una foto de perfil desde tu galería o pegar un enlace web de imagen.")
            return render(request, 'idols/form.html', {'tg_id': tg_id, 'tg_username': tg_username})

        try:
            idol_obj = IdolProfile.objects.create(
                telegram_user_id=tg_id,
                owner_username=custom_owner or tg_username,
                stage_name=stage_name,
                group=group,
                bio=bio,
                tagline=tagline,
                status=status,
                aura_color=aura_color,
                specialty=specialty,
                welcome_message=welcome_message,
                photo=photo,
                banner=banner
            )
            UserRole.objects.get_or_create(telegram_id=tg_id, defaults={'role': 'idol', 'staff_role': 'none'})
            UserRole.objects.filter(telegram_id=tg_id).update(role='idol')
            grant_user_xp(request, tg_id, 30, reason="Creación de Idol")

            group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)
            if group_id:
                welcome_txt = (
                    f"👑 <b>¡NUEVA MUSA CONSAGRADA EN EL REINO!</b> 🌹\n\n"
                    f"Demos la bienvenida a la deslumbrante <b>{stage_name}</b>" + (f" ({group})" if group else "") + f".\n"
                    + (f"✨ <i>«{tagline}»</i>\n\n" if tagline else "\n") +
                    f"Ingresa a la corte para conocer sus aposentos y brindarle tu primera ofrenda."
                )
                send_telegram_msg(
                    chat_id=group_id,
                    text=welcome_txt,
                    button_text=f"🎭 Conocer a {stage_name}",
                    button_url="https://t.me/KingdomPleasure_bot?start=entrar"
                )

            messages.success(request, f"✨ ¡{stage_name} ha sido consagrada con éxito! (+30 EXP)")
            return redirect(f'/idols/{idol_obj.id}/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')
        except Exception as e:
            messages.error(request, f"Error al registrar: {str(e)}")

    return render(request, 'idols/form.html', {'tg_id': tg_id, 'tg_username': tg_username})



def idol_edit(request, idol_id):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    idol = get_object_or_404(IdolProfile, id=idol_id)
    is_admin = check_is_staff_or_admin(tg_id)

    # Validar permisos
    if tg_id != idol.telegram_user_id and not is_admin:
        messages.error(request, "⚠️ No tienes permiso para editar esta Musa.")
        return redirect(f'/idols/?tg_id={tg_id}')

    if request.method == 'POST':
        try:
            # 🛡️ Sanitización y recorte seguro a los límites de la base de datos (max 100 caracteres)
            raw_stage = request.POST.get('stage_name', idol.stage_name).strip()
            idol.stage_name = raw_stage[:100]

            raw_group = request.POST.get('group', idol.group or '').strip()
            idol.group = raw_group[:100] if raw_group else None

            # Limpiar usuario de telegram (eliminar https://t.me/ si lo pegaron completo)
            raw_owner = request.POST.get('owner_username', idol.owner_username or '').strip()
            raw_owner = raw_owner.replace('https://t.me/', '').replace('http://t.me/', '').replace('t.me/', '').strip('/')
            if raw_owner and not raw_owner.startswith('@'):
                raw_owner = f"@{raw_owner}"
            idol.owner_username = raw_owner[:100] if raw_owner else None

            raw_specialty = request.POST.get('specialty', idol.specialty or '').strip()
            idol.specialty = raw_specialty[:100] if raw_specialty else None

            raw_tagline = request.POST.get('tagline', idol.tagline or '').strip()
            idol.tagline = raw_tagline[:120] if raw_tagline else None

            raw_welcome = request.POST.get('welcome_message', idol.welcome_message or '').strip()
            idol.welcome_message = raw_welcome[:200] if raw_welcome else None

            idol.bio = request.POST.get('bio', idol.bio).strip()[:500]
            idol.status = request.POST.get('status', idol.status)
            idol.aura_color = request.POST.get('aura_color', idol.aura_color)

            # Retrato con nombre corto
            photo_file = request.FILES.get('photo')
            photo_url = request.POST.get('photo_url', '').strip()
            if not photo_file and photo_url:
                photo_file = download_image_from_url(photo_url, default_filename=f"p_{uuid.uuid4().hex[:8]}.webp")
            if photo_file:
                opt_photo = optimize_uploaded_image(photo_file)
                if opt_photo:
                    idol.photo = opt_photo

            # Banner con nombre corto
            banner_file = request.FILES.get('banner')
            banner_url = request.POST.get('banner_url', '').strip()
            if not banner_file and banner_url:
                banner_file = download_image_from_url(banner_url, default_filename=f"b_{uuid.uuid4().hex[:8]}.webp")
            if banner_file:
                opt_banner = optimize_uploaded_image(banner_file)
                if opt_banner:
                    idol.banner = opt_banner

            idol.save()
            messages.success(request, f"✨ ¡Ficha de {idol.stage_name} actualizada con éxito!")
            return redirect(f'/idols/{idol.id}/?tg_id={tg_id}')
        except Exception as e:
            messages.error(request, f"⚠️ Error al guardar: {str(e)}")

    return render(request, 'idols/form.html', {
        'idol': idol,
        'tg_id': tg_id,
        'tg_username': idol.owner_username or f"@{tg_id}",
    })


def idol_delete(request, idol_id):
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id, telegram_user_id=tg_id)
    
    if request.method == 'POST':
        idol.delete()
        return redirect(f'/idols/?tg_id={tg_id}')
        
    return render(request, 'idols/confirm_delete.html', {'tg_id': tg_id, 'idol': idol})


def idol_gallery(request):
    tg_id = resolve_safe_tg(request)
    sort_by = request.GET.get('sort', 'rating')
    owner_filter = request.GET.get('owner', '').strip()

    query = IdolProfile.objects.annotate(
        total_unlocks=Count('posts__unlocks')
    )

    if owner_filter:
        query = query.filter(owner_username__icontains=owner_filter)

    all_idols = list(query)
    max_unlocks = max([i.total_unlocks for i in all_idols], default=0)

    for idol in all_idols:
        idol.is_trending = (max_unlocks > 0 and idol.total_unlocks == max_unlocks)
        idol.is_top_rated = (idol.rating >= 4.80 and idol.services_done >= 2)

    def get_sort_key(item):
        is_feat = 1 if item.is_featured else 0
        if sort_by == 'owner':
            return (is_feat, str(item.owner_username).lower(), item.stage_name.lower())
        elif sort_by == 'services':
            return (is_feat, item.services_done, float(item.rating))
        elif sort_by == 'recent':
            return (is_feat, item.created_at)
        else: # rating
            return (is_feat, float(item.rating), item.total_unlocks)

    all_idols.sort(key=get_sort_key, reverse=True)
    all_owners = list(IdolProfile.objects.exclude(owner_username__isnull=True).exclude(owner_username='').values_list('owner_username', flat=True).distinct())

    return render(request, 'idols/gallery.html', {
        'all_idols': all_idols,
        'tg_id': tg_id,
        'sort_by': sort_by,
        'owner_filter': owner_filter,
        'all_owners': all_owners,
    })


def idol_detail(request, idol_id):
    tg_id = resolve_safe_tg(request)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    tg_username = request.GET.get('tg_username') or request.POST.get('tg_username') or (profile.username if profile else 'Noble')
    active_tab = request.GET.get('tab', 'muro')

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
    is_admin = check_is_staff_or_admin(tg_id)
    can_edit = bool(tg_id and (tg_id == idol.telegram_user_id or is_admin))

    if request.method == 'POST':
        try:
            rating_val = int(request.POST.get('rating', 5))
            comment_val = request.POST.get('comment', '').strip()
            if not comment_val:
                messages.error(request, "Debes escribir un comentario sobre la atención.")
            elif rating_val < 1 or rating_val > 5:
                messages.error(request, "La calificación debe ser entre 1 y 5 estrellas.")
            elif tg_id and tg_id == idol.telegram_user_id:
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
                    button_url=f"https://kingdom-pleasure-app.onrender.com/idols/{idol.id}/?tg_id={idol.telegram_user_id}&tab=resenas"
                )
                messages.success(request, "¡Tu reseña fue publicada con éxito (+15 EXP)!")
                return redirect(f'/idols/{idol_id}/?tg_id={tg_id}&tg_username={encode_param(tg_username)}&tab=resenas')
        except Exception as e:
            messages.error(request, f"Error al procesar reseña: {str(e)}")

        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}&tg_username={encode_param(tg_username)}')

    # Solicitudes de Rol para la dueña de la Idol
    roleplay_requests = []
    if can_edit:
        try:
            roleplay_requests = list(RoleSessionRequest.objects.filter(idol=idol).order_by('-created_at')[:8])
        except Exception:
            roleplay_requests = []

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
        'can_edit': can_edit,
        'active_tab': active_tab,
        'roleplay_requests': roleplay_requests,
    }
    return render(request, 'idols/detail.html', context)


def social_feed(request):
    """
    Muro VIP Clandestino de la Corte.
    Integra saldo en tiempo real, catálogo de musas para filtro instantáneo,
    y prefetch blindado de reacciones, desbloqueos y comentarios.
    """
    tg_id = resolve_safe_tg(request)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    tg_username = request.GET.get('tg_username') or (profile.username if profile else 'Noble')
    
    wallet = Wallet.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    my_balance = wallet.balance if wallet else 0

    # ✅ CORREGIDO: IdolProfile no tiene 'is_active', se cargan todas las musas ordenadas
    try:
        all_idols = IdolProfile.objects.all().order_by('stage_name')
    except Exception:
        all_idols = []

    # Prefetch blindado con fallback
    try:
        posts = Post.objects.all().select_related('idol').prefetch_related(
            'comments', 'gallery', 'user_likes'
        )
    except Exception:
        posts = Post.objects.all().select_related('idol')

    idol_filter_id = request.GET.get('idol_id')
    filtered_idol = None
    if idol_filter_id and str(idol_filter_id).isdigit():
        filtered_idol = IdolProfile.objects.filter(id=int(idol_filter_id)).first()
        if filtered_idol:
            posts = posts.filter(idol=filtered_idol)

    unlocked_ids = set()
    liked_ids = []
    user_reactions = {}
    is_admin = check_is_staff_or_admin(tg_id)
    
    if tg_id:
        try:
            pagados = list(PostUnlock.objects.filter(client_telegram_id=tg_id).values_list('post_id', flat=True))
            propios = list(Post.objects.filter(idol__telegram_user_id=tg_id).values_list('id', flat=True))
            unlocked_ids = set(pagados + propios)
        except Exception:
            unlocked_ids = set()
            
        try:
            user_likes_objs = PostLike.objects.filter(client_telegram_id=tg_id)
            liked_ids = list(user_likes_objs.values_list('post_id', flat=True))
            user_reactions = {like.post_id: getattr(like, 'reaction_type', 'like') for like in user_likes_objs}
        except Exception:
            liked_ids = []
            user_reactions = {}

    # Inyectar propiedades directamente en cada post
    posts_list = []
    for p in posts:
        # Verificación segura de autoría (Idol propietaria o Admin)
        is_owner = bool(tg_id and p.idol and str(p.idol.telegram_user_id) == str(tg_id))
        p.can_manage = bool(is_admin or is_owner)
        p.is_unlocked = bool(p.id in unlocked_ids or p.network == 'gram' or is_admin or is_owner)
        p.is_liked = bool(p.id in liked_ids)
        p.user_reaction = user_reactions.get(p.id, 'like' if p.id in liked_ids else '')
        posts_list.append(p)

    theme_active = KingdomSetting.get_val('feed_theme_active', 'false') == 'true'
    feed_theme = {
        'is_active': theme_active,
        'title': KingdomSetting.get_val('feed_theme_title', 'Temática Semanal'),
        'message': KingdomSetting.get_val('feed_theme_message', ''),
        'banner_url': KingdomSetting.get_val('feed_theme_banner', '')
    }
    
    return render(request, 'idols/feed.html', {
        'posts': posts_list,
        'tg_id': tg_id,
        'unlocked_ids': list(unlocked_ids),
        'liked_ids': liked_ids,
        'user_reactions': user_reactions,
        'tg_username': tg_username,
        'is_admin': is_admin,
        'feed_theme': feed_theme,
        'filtered_idol': filtered_idol,
        'all_idols': all_idols,
        'my_balance': my_balance,
        'wallet': wallet,
        'profile': profile,
    })


def delete_post(request, post_id):
    tg_id = resolve_safe_tg(request)
    post = get_object_or_404(Post, id=post_id)
    
    is_admin = check_is_staff_or_admin(tg_id)
    is_owner = bool(tg_id and post.idol and str(tg_id) == str(post.idol.telegram_user_id))

    if not (is_admin or is_owner):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1':
            return JsonResponse({'success': False, 'error': "No tienes permiso para eliminar esta publicación."}, status=403)
        messages.error(request, "No tienes permiso para eliminar esta publicación.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    if request.method == 'POST':
        post.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1':
            return JsonResponse({'success': True, 'message': "🗑️ Publicación eliminada del Muro con éxito."})
        messages.success(request, "🗑️ Publicación eliminada del Muro con éxito.")
        
    return redirect(f'/idols/feed/?tg_id={tg_id}')


def edit_post(request, post_id):
    tg_id = resolve_safe_tg(request)
    post = get_object_or_404(Post, id=post_id)
    
    is_admin = check_is_staff_or_admin(tg_id)
    is_owner = bool(tg_id and post.idol and str(tg_id) == str(post.idol.telegram_user_id))

    if not (is_admin or is_owner):
        messages.error(request, "No tienes permiso para editar esta publicación.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    creator_profile = UserProfile.objects.filter(telegram_user_id=post.idol.telegram_user_id).first()
    max_price = creator_profile.max_post_price_allowed if creator_profile else 100

    if request.method == 'POST':
        post.caption = request.POST.get('caption', '').strip()
        network = request.POST.get('network', post.network)
        price = request.POST.get('price', post.price)

        if 'image' in request.FILES:
            post.image = optimize_uploaded_image(request.FILES['image'])
            post.video = None
        elif 'video' in request.FILES:
            post.video = request.FILES['video']
            post.image = None

        post.network = network
        if network == 'fans':
            try:
                p_val = int(price)
                post.price = max(1, min(p_val, max_price))
            except Exception:
                post.price = 50
        else:
            post.price = 0

        post.save()
        messages.success(request, "✨ Publicación actualizada con éxito.")
        return redirect(f'/idols/feed/?tg_id={tg_id}')

    return render(request, 'idols/edit_post.html', {
        'post': post,
        'tg_id': tg_id,
        'max_price': max_price
    })


def unlock_post(request, post_id):
    """Desbloqueo de publicaciones VIP (soporta tanto envío normal como AJAX sin recarga)."""
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        tg_id = resolve_safe_tg(request)
        post = get_object_or_404(Post, id=post_id)
        
        if tg_id and tg_id == post.idol.telegram_user_id:
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'already_unlocked': True,
                    'media_urls': post.all_images,
                    'is_video': post.is_video,
                    'video_url': post.video.url if post.video else ''
                })
            messages.info(request, "Esta publicación es de tu Idol, ya la tienes desbloqueada.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
        
        wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if post.network == 'fans':
            pet = Pet.objects.filter(telegram_user_id=tg_id).first()
            precio_final = post.price

            if pet and pet.species == 'viper':
                discount_rates = {1: 0.85, 2: 0.78, 3: 0.70}
                rate = discount_rates.get(pet.evolution_stage_number, 0.85)
                precio_final = max(1, int(post.price * rate))

            if wallet.balance >= precio_final:
                wallet.remove_funds(precio_final)
                
                if pet and pet.species == 'scorpion':
                    cb_rates = {1: 0.05, 2: 0.10, 3: 0.15}
                    reembolso = int(precio_final * cb_rates.get(pet.evolution_stage_number, 0.05))
                    if reembolso > 0:
                        wallet.add_funds(reembolso)

                PostUnlock.objects.get_or_create(post=post, client_telegram_id=tg_id)
                
                idol_profile = UserProfile.objects.filter(telegram_user_id=post.idol.telegram_user_id).first()
                tasa_idol = idol_profile.idol_commission_rate if idol_profile else 0.85
                ganancia_idol = int(precio_final * tasa_idol)
                
                idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
                idol_wallet.add_funds(ganancia_idol)
                
                grant_user_xp(request, tg_id, max(5, precio_final // 10), reason="Desbloqueo VIP")
                grant_user_xp(None, post.idol.telegram_user_id, max(5, precio_final // 10), reason="Venta de Contenido VIP")

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
                
                desc_txt = f" (con descuento por tu {pet.evolved_name})" if (pet and pet.species == 'viper') else ""
                
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'new_balance': wallet.balance,
                        'precio_pagado': precio_final,
                        'media_urls': post.all_images,
                        'is_video': post.is_video,
                        'video_url': post.video.url if post.video else '',
                        'message': f"¡Foto desbloqueada con éxito! (-{precio_final} 🪙{desc_txt})"
                    })
                messages.success(request, f"¡Foto desbloqueada con éxito! (-{precio_final} 🪙{desc_txt})")
            else:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'No tienes suficiente oro en tu Bóveda.'}, status=400)
                messages.error(request, "No tienes suficiente oro en tu Bóveda.")
        else:
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'media_urls': post.all_images,
                    'is_video': post.is_video,
                    'video_url': post.video.url if post.video else ''
                })
                
    return redirect(f'/idols/feed/?tg_id={tg_id}')


def create_post(request):
    """Creación de posts con soporte para carruseles de 1 a 5 fotografías."""
    tg_id = resolve_safe_tg(request)
    mis_idols = IdolProfile.objects.filter(telegram_user_id=tg_id)
    
    if not mis_idols.exists():
        messages.error(request, "Debes registrar al menos una Idol antes de publicar.")
        return redirect(f'/idols/?tg_id={tg_id}')
        
    creator_profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
    max_price = creator_profile.max_post_price_allowed if creator_profile else 100

    if request.method == 'POST':
        idol_id = request.POST.get('idol_id')
        network = request.POST.get('network')
        caption = request.POST.get('caption', '').strip()
        media_type = request.POST.get('media_type', 'image')
        
        # Múltiples fotos para carrusel o foto simple tradicional
        raw_images = request.FILES.getlist('images')
        if not raw_images and request.FILES.get('image'):
            raw_images = [request.FILES.get('image')]
            
        raw_video = request.FILES.get('video')
        price = request.POST.get('price', 50)

        if not price or str(price).strip() == '':
            price = 50
        
        try:
            idol = mis_idols.get(id=idol_id)

            if media_type == 'video':
                if not raw_video:
                    messages.error(request, "Debes adjuntar un archivo de video (MP4 o WebM).")
                    return render(request, 'idols/create_post.html', {'tg_id': tg_id, 'mis_idols': mis_idols, 'max_price': max_price})
                post_image = None
                post_video = raw_video
            else:
                if not raw_images:
                    messages.error(request, "Debes adjuntar al menos una fotografía.")
                    return render(request, 'idols/create_post.html', {'tg_id': tg_id, 'mis_idols': mis_idols, 'max_price': max_price})
                # Primera foto como portada principal del post
                post_image = optimize_uploaded_image(raw_images[0])
                post_video = None

            if network == 'fans' and int(price) > max_price:
                messages.error(request, f"Tu rango actual solo permite fijar precios de hasta {max_price} 🪙 por publicación.")
            else:
                new_post = Post.objects.create(
                    idol=idol,
                    network=network,
                    caption=caption,
                    image=post_image,
                    video=post_video,
                    price=int(price) if network == 'fans' else 0
                )
                
                # Guardar fotos complementarias para el carrusel (fotos 2 a 5)
                if media_type != 'video' and len(raw_images) > 1:
                    for idx, extra_img in enumerate(raw_images[1:5], start=1):
                        opt_extra = optimize_uploaded_image(extra_img)
                        PostImage.objects.create(post=new_post, image=opt_extra, order=idx)

                xp_awarded = 25 if len(raw_images) > 1 else (20 if media_type == 'video' else 15)
                grant_user_xp(request, tg_id, xp_awarded, reason="Nuevo Post Publicado")

                # Notificación al Grupo Oficial de Telegram
                group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)
                if group_id:
                    clean_caption = (caption[:110] + '...') if len(caption) > 110 else caption
                    multi_tag = f" 📸 ({len(raw_images)} Fotos)" if len(raw_images) > 1 else ""
                    if network == 'fans':
                        post_text = (
                            f"🔞 <b>¡Nueva Sesión VIP en KingdomFans!</b> 💎\n\n"
                            f"🌹 <b>Musa:</b> {idol.stage_name} ({idol.group or 'Solista'}){multi_tag}\n"
                            f"🪙 <b>Tarifa:</b> <b>{price} 🪙</b>\n"
                            f"📝 <i>«{clean_caption}»</i>\n\n"
                            f"Cruza el umbral para desbloquear el contenido exclusivo para tu Colección."
                        )
                        btn_label = f"💎 Ver Contenido de {idol.stage_name}"
                    else:
                        post_text = (
                            f"📸 <b>¡Nueva Publicación en KingdomGram!</b> ✨\n\n"
                            f"🌹 <b>Musa:</b> {idol.stage_name} ({idol.group or 'Solista'}){multi_tag}\n"
                            f"📝 <i>«{clean_caption}»</i>\n\n"
                            f"Visita el Muro para admirar la sesión y dejarle tus halagos."
                        )
                        btn_label = f"📱 Ver Muro de {idol.stage_name}"

                    send_telegram_msg(
                        chat_id=group_id,
                        text=post_text,
                        button_text=btn_label,
                        button_url="https://t.me/KingdomPleasure_bot?start=entrar"
                    )

                messages.success(request, f"¡Publicación realizada exitosamente como {idol.stage_name}!")
                return redirect(f'/idols/feed/?tg_id={tg_id}')
                
        except IdolProfile.DoesNotExist:
            messages.error(request, "Idol seleccionada inválida.")
        except ValueError:
            messages.error(request, "El precio ingresado no es válido.")
            
    return render(request, 'idols/create_post.html', {'tg_id': tg_id, 'mis_idols': mis_idols, 'max_price': max_price})


def toggle_like(request, post_id):
    """Mantiene compatibilidad con el endpoint anterior de Like simple."""
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
            PostLike.objects.create(post=post, client_telegram_id=tg_id, reaction_type='like')
            post.likes += 1
            post.save()
            liked = True
            grant_user_xp(request, tg_id, 2, reason="Me Gusta en Muro")
            
        return JsonResponse({'liked': liked, 'likes': post.likes})
        
    return JsonResponse({'error': 'Invalid method'}, status=405)


def toggle_reaction(request, post_id):
    """
    Gestiona la Barra de Reacciones V.I.P de la Corte (❤️, 🔥, 👑, 🥂, 🤤).
    Devuelve active_reaction y current_reaction perfectamente sincronizados.
    """
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        if not tg_id:
            return JsonResponse({'success': False, 'error': 'No user ID provided'}, status=400)
            
        post = get_object_or_404(Post, id=post_id)
        reaction = request.POST.get('reaction', 'like').strip()
        allowed = ['like', 'fire', 'crown', 'toast', 'drool']
        if reaction not in allowed:
            reaction = 'like'

        existing_like = PostLike.objects.filter(post=post, client_telegram_id=tg_id).first()
        
        if existing_like:
            if existing_like.reaction_type == reaction:
                # Quitar reacción
                existing_like.delete()
                if post.likes > 0:
                    post.likes -= 1
                    post.save()
                active = False
                current_reaction = None
            else:
                # Cambiar de reacción
                existing_like.reaction_type = reaction
                existing_like.save()
                active = True
                current_reaction = reaction
        else:
            # Nueva reacción
            PostLike.objects.create(post=post, client_telegram_id=tg_id, reaction_type=reaction)
            post.likes += 1
            post.save()
            active = True
            current_reaction = reaction
            grant_user_xp(request, tg_id, 2, reason="Reacción en Muro")

        return JsonResponse({
            'success': True,
            'active': active,
            'current_reaction': current_reaction,
            'active_reaction': current_reaction,
            'total_likes': post.likes
        })
        
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
    """Brindis / Propina para la Musa (soporta AJAX para lluvia de monedas en vivo)."""
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        tg_id = resolve_safe_tg(request)
        post = get_object_or_404(Post, id=post_id)
        
        try:
            amount = int(request.POST.get('tip_amount', 0))
        except ValueError:
            amount = 0
            
        if amount <= 0:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'El monto del brindis debe ser mayor a 0.'}, status=400)
            messages.error(request, "El monto del brindis debe ser mayor a 0.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        if tg_id and tg_id == post.idol.telegram_user_id:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'No puedes enviarte ofrendas a ti mismo.'}, status=400)
            messages.info(request, "No puedes enviarte ofrendas a ti mismo.")
            return redirect(f'/idols/feed/?tg_id={tg_id}')
            
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        
        if client_wallet.remove_funds(amount):
            comision = int(amount * 0.10)
            neto_idol = amount - comision
            
            pet = Pet.objects.filter(telegram_user_id=tg_id).first()
            if pet and pet.species == 'scorpion':
                cb_rates = {1: 0.05, 2: 0.10, 3: 0.15}
                reembolso = int(amount * cb_rates.get(pet.evolution_stage_number, 0.05))
                if reembolso > 0:
                    client_wallet.add_funds(reembolso)

            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=post.idol.telegram_user_id)
            idol_wallet.add_funds(neto_idol)
            
            grant_user_xp(request, tg_id, max(2, amount // 20), reason="Ofrenda a Musa")
            grant_user_xp(None, post.idol.telegram_user_id, max(2, amount // 20), reason="Ofrenda Recibida")

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
            msg = f"🥂 ¡Le has invitado un trago de {amount} 🪙 a {post.idol.stage_name}!"
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'new_balance': client_wallet.balance,
                    'amount': amount,
                    'message': msg
                })
            messages.success(request, msg)
        else:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'No tienes suficiente oro en tu Bóveda.'}, status=400)
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
        if bounty < 100 or not description:
            messages.error(request, "La ofrenda mínima para un antojo es de 100 🪙 y requiere una descripción.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
            
        client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
        if not client_wallet.remove_funds(bounty):
            messages.error(request, f"No tienes suficiente oro ({bounty} 🪙) en tu Bóveda.")
            return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

        from economy.models import UserInventoryItem
        has_priority_stamp = UserInventoryItem.consume_item(tg_id, 'priority_antojo', 1)
            
        CustomRequest.objects.create(
            idol=idol,
            client_telegram_id=tg_id,
            client_username=tg_username,
            description=description,
            bounty=bounty,
            is_priority=has_priority_stamp,
            status='pending'
        )

        extra_pri_msg = "⚡ (¡Sello Prioritario aplicado! Tu solicitud aparecerá primera en su bandeja)" if has_priority_stamp else ""

        send_telegram_msg(
            chat_id=idol.telegram_user_id,
            text=(
                f"{'⚡ <b>¡PETICIÓN PRIORITARIA DE ANTOJO!</b> ⚡' if has_priority_stamp else '📬 <b>¡Nueva Petición Especial!</b>'}\n\n"
                f"🌹 <b>Para tu Musa:</b> {idol.stage_name}\n"
                f"👤 <b>Solicitante:</b> {tg_username}\n"
                f"🪙 <b>Recompensa en custodia:</b> <b>+{bounty} 🪙</b>\n"
                f"📝 <b>Detalle:</b> <i>«{description}»</i>\n\n"
                f"Ingresa a tu panel de Idols para atenderla."
            ),
            button_text=f"📸 Atender Petición de {idol.stage_name}",
            button_url=f"https://kingdom-pleasure-app.onrender.com/idols/?tg_id={idol.telegram_user_id}"
        )
        messages.success(request, f"¡Petición enviada a {idol.stage_name}! Tu oro quedó en custodia. {extra_pri_msg}")
        
    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')


def add_comment(request, post_id):
    """
    Comentarios en vivo vía AJAX con marco, título nobiliario y nivel real.
    """
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        tg_id = resolve_safe_tg(request)
        profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
        tg_username = request.POST.get('tg_username') or (profile.username if profile else 'Noble')
        text = request.POST.get('text', '').strip()
        parent_id = request.POST.get('parent_id')
        post = get_object_or_404(Post, id=post_id)
        
        if text:
            nombre_final = f"{post.idol.stage_name} (Idol)" if (tg_id and tg_id == post.idol.telegram_user_id) else tg_username
            
            parent_comment = None
            if parent_id and str(parent_id).isdigit():
                parent_comment = PostComment.objects.filter(id=int(parent_id), post=post).first()

            is_vip = bool(profile and profile.has_vip_badge)

            new_comment = PostComment.objects.create(
                post=post,
                parent=parent_comment,
                author_telegram_id=tg_id if tg_id else 0,
                author_name=nombre_final,
                is_vip_author=is_vip,
                text=text
            )
            grant_user_xp(request, tg_id, 3, reason="Comentario en Muro")

            # Notificación Telegram
            if parent_comment and parent_comment.author_telegram_id and parent_comment.author_telegram_id != tg_id:
                send_telegram_msg(
                    chat_id=parent_comment.author_telegram_id,
                    text=(
                        f"💬 <b>¡Respondieron a tu comentario!</b>\n\n"
                        f"👤 <b>{nombre_final}</b> te respondió en la publicación de {post.idol.stage_name}:\n"
                        f"<i>«{text}»</i>"
                    ),
                    button_text="📱 Ver Respuesta",
                    button_url=f"https://kingdom-pleasure-app.onrender.com/idols/feed/?tg_id={parent_comment.author_telegram_id}"
                )
            elif tg_id != post.idol.telegram_user_id:
                send_telegram_msg(
                    chat_id=post.idol.telegram_user_id,
                    text=(
                        f"💬 <b>¡Nuevo halago para tu Musa {post.idol.stage_name}!</b>\n\n"
                        f"👤 <b>Usuario:</b> {nombre_final}\n"
                        f"📝 <i>«{text}»</i>"
                    ),
                    button_text="📱 Ver Publicación",
                    button_url=f"https://kingdom-pleasure-app.onrender.com/idols/feed/?tg_id={post.idol.telegram_user_id}"
                )

            if is_ajax:
                author_title = profile.get_title_display() if (profile and profile.title) else ''
                author_level = profile.level if profile else 1
                avatar_frame = profile.avatar_frame if profile else 'gold'

                return JsonResponse({
                    'success': True,
                    'comment': {
                        'id': new_comment.id,
                        'parent_id': parent_comment.id if parent_comment else None,
                        'author_name': new_comment.author_name,
                        'is_vip_author': new_comment.is_vip_author,
                        'level': author_level,
                        'author_level': author_level,
                        'title': author_title,
                        'author_title': author_title,
                        'avatar_frame': avatar_frame,
                        'text': new_comment.text,
                        'created_at': 'hace un instante'
                    },
                    'total_comments': post.comments.count()
                })

            messages.success(request, "Comentario publicado (+3 EXP).")
            
    return redirect(f'/idols/feed/?tg_id={tg_id}&tg_username={tg_username}')


# ==========================================
# SISTEMA DE PHOTOCARDS Y CAJAS CS
# ==========================================

def photocard_boxes_view(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    boxes = PhotocardBox.objects.filter(is_active=True).prefetch_related('cards')
    
    is_admin = check_is_staff_or_admin(tg_id)
    my_cards_count = UserPhotocard.objects.filter(telegram_user_id=tg_id).count()

    upcoming_active = KingdomSetting.get_val('upcoming_box_active', 'false') == 'true'
    upcoming_data = {
        'is_active': upcoming_active,
        'title': KingdomSetting.get_val('upcoming_box_title', ''),
        'release_date': KingdomSetting.get_val('upcoming_box_date', ''),
        'description': KingdomSetting.get_val('upcoming_box_desc', ''),
        'image_url': KingdomSetting.get_val('upcoming_box_image', '')
    }

    return render(request, 'idols/photocard_boxes.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'boxes': boxes,
        'is_admin': is_admin,
        'my_cards_count': my_cards_count,
        'upcoming': upcoming_data,
    })


def open_photocard_box_ajax(request, box_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return JsonResponse({'success': False, 'error': 'Sesión no identificada'}, status=400)

    try:
        count = int(request.POST.get('count', 1))
        if count not in [1, 5, 10]:
            count = 1
    except Exception:
        count = 1

    box = get_object_or_404(PhotocardBox, id=box_id, is_active=True)
    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    total_cost = box.price * count
    if wallet.balance < total_cost:
        return JsonResponse({
            'success': False, 
            'error': f'No tienes suficiente oro en tu Bóveda. Necesitas {total_cost} 🪙 para abrir {count} cajas (tienes {wallet.balance} 🪙).'
        }, status=400)

    all_cards = list(box.cards.all())
    if not all_cards:
        return JsonResponse({'success': False, 'error': 'Esta caja aún no tiene cartas cargadas.'}, status=400)

    wallet.remove_funds(total_cost)

    # Bonos de mascota y amuleto
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()
    extra_legendary_base = {1: 5.0, 2: 12.0, 3: 20.0}.get(pet.evolution_stage_number, 5.0) if (pet and pet.species == 'rabbit') else 0.0

    from economy.models import UserInventoryItem
    has_lucky_key = UserInventoryItem.consume_item(tg_id, 'lucky_charm')
    if has_lucky_key:
        extra_legendary_base += 15.0

    already_owned_ids = set(UserPhotocard.objects.filter(telegram_user_id=tg_id).values_list('photocard_id', flat=True))

    xp_map = {'common': 5, 'rare': 12, 'epic': 25, 'legendary': 50}
    total_xp = 0
    winners = []
    legendary_winners = []

    for _ in range(count):
        roll = random.random() * 100
        p_legendary = 3.0 + extra_legendary_base
        p_epic = p_legendary + 12.0
        p_rare = p_epic + 25.0

        if roll < p_legendary:
            target_rarity = 'legendary'
        elif roll < p_epic:
            target_rarity = 'epic'
        elif roll < p_rare:
            target_rarity = 'rare'
        else:
            target_rarity = 'common'

        pool = [c for c in all_cards if c.rarity == target_rarity]
        card = random.choice(pool) if pool else random.choice(all_cards)

        is_new = (card.id not in already_owned_ids)
        already_owned_ids.add(card.id)

        UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=card)

        earned_xp = xp_map.get(card.rarity, 10)
        total_xp += earned_xp
        grant_user_xp(request, tg_id, earned_xp, reason=f"Photocard {card.get_rarity_display()}")

        card_dict = {
            'id': card.id,
            'name': card.name,
            'rarity': card.rarity,
            'rarity_display': card.get_rarity_display(),
            'color': card.get_color_hex(),
            'image_url': card.image.url if card.image else '',
            'idol_name': card.display_idol_name,
            'is_new': is_new,
        }
        winners.append(card_dict)

        if card.rarity == 'legendary':
            legendary_winners.append(card)

    if legendary_winners:
        group_id = getattr(settings, 'TELEGRAM_GROUP_ID', None)
        if group_id:
            user_prof = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            noble_name = user_prof.username if user_prof else f"Noble_{tg_id}"
            names_str = ", ".join([f"«{w.name}» ({w.display_idol_name})" for w in legendary_winners])
            send_telegram_msg(
                chat_id=group_id,
                text=(
                    f"👑🎉 <b>¡DESENTIERRO LEGENDARIO EN EL REINO!</b> 🎉👑\n\n"
                    f"El afortunado <b>{noble_name}</b> abrió el relicario <i>«{box.name}»</i> (x{count}) y obtuvo:\n\n"
                    f"🎴 <b>{names_str}</b>\n\n"
                    f"¡Rindamos honores a su increíble fortuna en los relicarios!"
                ),
                button_text="🎁 Probar Mi Suerte en Cajas",
                button_url="https://t.me/KingdomPleasure_bot?start=entrar"
            )

    # Muestra de cartas para el relleno visual del carrusel
    sample_cards = [{
        'id': c.id,
        'name': c.name,
        'rarity': c.rarity,
        'rarity_display': c.get_rarity_display(),
        'color': c.get_color_hex(),
        'image_url': c.image.url if c.image else '',
        'idol_name': c.display_idol_name,
    } for c in all_cards]

    first_winner = winners[0]
    rarity_ranks = {'legendary': 4, 'epic': 3, 'rare': 2, 'common': 1}
    highest_card = max(winners, key=lambda w: rarity_ranks.get(w['rarity'], 1))

    return JsonResponse({
        'success': True,
        'count': count,
        'nuevo_saldo': wallet.balance,
        'total_xp': total_xp,
        'highest_rarity': highest_card['rarity'],
        'highest_color': highest_card['color'],
        'winner': first_winner,
        'winners': winners,
        'sample_cards': sample_cards,
    })


def my_photocards_album(request):
    try:
        tg_id = resolve_safe_tg(request)
        if not tg_id:
            return redirect('/')

        raw_user_cards = list(UserPhotocard.objects.filter(
            telegram_user_id=tg_id,
            photocard__isnull=False
        ).select_related('photocard', 'photocard__idol', 'photocard__box').order_by('-obtained_at'))

        user_cards = [uc for uc in raw_user_cards if getattr(uc, 'photocard', None) is not None]

        RARITY_PRIORITY = {
            'legendary': 1,
            'epic': 2,
            'rare': 3,
            'common': 4,
        }

        def card_canonical_sort_key(uc):
            p = getattr(uc, 'photocard', None)
            if not p:
                return (99, '', '', 0)
            r_val = RARITY_PRIORITY.get(getattr(p, 'rarity', 'common'), 5)
            idol_name = (getattr(p, 'display_idol_name', '') or '').lower().strip()
            card_name = (getattr(p, 'name', '') or '').lower().strip()
            return (r_val, idol_name, card_name, p.id)

        for uc in user_cards:
            try:
                uc.safe_image_url = uc.photocard.image.url if (uc.photocard and uc.photocard.image) else ''
            except Exception:
                uc.safe_image_url = ''
            uc.rarity_weight = RARITY_PRIORITY.get(getattr(uc.photocard, 'rarity', 'common'), 5)
            uc.is_owned = True

        total = len(user_cards)
        legendaries = sum(1 for uc in user_cards if getattr(uc.photocard, 'rarity', '') == 'legendary')
        epics = sum(1 for uc in user_cards if getattr(uc.photocard, 'rarity', '') == 'epic')

        cards_by_photocard = {}
        for uc in user_cards:
            cards_by_photocard.setdefault(uc.photocard_id, []).append(uc)

        duplicates_list = []
        duplicate_cards_count = 0
        for p_id, ucs in cards_by_photocard.items():
            if len(ucs) > 1:
                rep_obj = ucs[0]
                rep_obj.copies_total = len(ucs)
                rep_obj.copies_extra = len(ucs) - 1
                duplicates_list.append(rep_obj)
                duplicate_cards_count += (len(ucs) - 1)

        duplicates_list.sort(key=card_canonical_sort_key)

        class MissingPhotocardSlot:
            """Representa un slot de carta faltante/bloqueada en el álbum."""
            def __init__(self, photocard):
                self.id = 0
                self.is_owned = False
                self.photocard = photocard
                self.photocard_id = photocard.id
                self.copies_count = 0
                self.is_for_sale = False
                self.sale_price = 0
                self.obtained_at = photocard.created_at
                try:
                    self.safe_image_url = photocard.image.url if photocard.image else ''
                except Exception:
                    self.safe_image_url = ''
                self.rarity_weight = RARITY_PRIORITY.get(getattr(photocard, 'rarity', 'common'), 5)

        all_boxes = list(PhotocardBox.objects.all().prefetch_related('cards').order_by('name'))
        collections_data = []

        for box in all_boxes:
            all_box_cards = list(box.cards.all())
            total_in_box = len(all_box_cards)
            box_ucs = [uc for uc in user_cards if getattr(uc.photocard, 'box_id', None) == box.id]

            distinct_cards_owned = {}
            for uc in box_ucs:
                if uc.photocard_id not in distinct_cards_owned:
                    uc.is_owned = True
                    uc.copies_count = len(cards_by_photocard.get(uc.photocard_id, []))
                    distinct_cards_owned[uc.photocard_id] = uc

            # Construir la cuadrícula completa de la caja (obtenidas + bloqueadas)
            box_slots = []
            for pc in all_box_cards:
                if pc.id in distinct_cards_owned:
                    box_slots.append(distinct_cards_owned[pc.id])
                else:
                    box_slots.append(MissingPhotocardSlot(pc))

            box_slots.sort(key=card_canonical_sort_key)

            owned_count = len(distinct_cards_owned)
            missing_count = max(0, total_in_box - owned_count)
            percent = int((owned_count / total_in_box) * 100) if total_in_box > 0 else 0

            if owned_count > 0 or total_in_box > 0:
                collections_data.append({
                    'box': box,
                    'total_cards': total_in_box,
                    'owned_count': owned_count,
                    'missing_count': missing_count,
                    'percent': percent,
                    'is_complete': (owned_count == total_in_box and total_in_box > 0),
                    'user_cards': box_slots,
                })

        orphan_ucs = [uc for uc in user_cards if not getattr(uc.photocard, 'box_id', None)]
        if orphan_ucs:
            orphan_distinct = {}
            for uc in orphan_ucs:
                if uc.photocard_id not in orphan_distinct:
                    uc.is_owned = True
                    uc.copies_count = len(cards_by_photocard.get(uc.photocard_id, []))
                    orphan_distinct[uc.photocard_id] = uc

            orphan_cards_sorted = list(orphan_distinct.values())
            orphan_cards_sorted.sort(key=card_canonical_sort_key)

            class OrphanBox:
                id = 0
                name = 'Colección Clandestina (Especial)'
                cover_image = None

            collections_data.append({
                'box': OrphanBox(),
                'total_cards': len(orphan_distinct),
                'owned_count': len(orphan_distinct),
                'missing_count': 0,
                'percent': 100,
                'is_complete': False,
                'user_cards': orphan_cards_sorted,
            })

        sorted_all_cards = list(user_cards)
        sorted_all_cards.sort(key=card_canonical_sort_key)

        members = UserProfile.objects.exclude(
            telegram_user_id=tg_id
        ).order_by('-level')[:60]

        pinned_card_ids = []
        try:
            profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            raw_pinned = profile.get_pinned_items() if (profile and hasattr(profile, 'get_pinned_items')) else (getattr(profile, 'pinned_items', []) if profile else [])
            if isinstance(raw_pinned, str):
                import json
                try:
                    raw_pinned = json.loads(raw_pinned)
                except Exception:
                    raw_pinned = []
            pinned_card_ids = [str(it.get('id')) for it in (raw_pinned or []) if isinstance(it, dict) and it.get('type') == 'photocard']
        except Exception:
            pinned_card_ids = []

        return render(request, 'idols/photocards_album.html', {
            'tg_id': tg_id,
            'user_cards': sorted_all_cards,
            'collections': collections_data,
            'duplicates': duplicates_list,
            'duplicate_cards_count': duplicate_cards_count,
            'unique_count': len(cards_by_photocard),
            'total': total,
            'legendaries': legendaries,
            'epics': epics,
            'members': members,
            'pinned_card_ids': pinned_card_ids,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f"Aviso del Álbum: {str(e)}")
        return redirect('/idols/photocards/')


def admin_photocards_manage(request):
    tg_id = resolve_safe_tg(request)
    is_admin = check_is_staff_or_admin(tg_id)

    if not is_admin:
        messages.error(request, "Solo los administradores pueden gestionar Photocards.")
        return redirect('/idols/photocards/')

    if request.method == 'POST':
        action = request.POST.get('action')

        try:
            if action == 'create_box':
                name = request.POST.get('name', '').strip()
                description = request.POST.get('description', '').strip()
                price = int(request.POST.get('price', 120))
                cover_image = optimize_uploaded_image(request.FILES.get('cover_image'))
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
                    box.cover_image = optimize_uploaded_image(request.FILES['cover_image'])
                box.save()
                messages.success(request, f"💾 Caja «{box.name}» actualizada.")

            elif action == 'delete_box':
                box_id = request.POST.get('box_id')
                box = get_object_or_404(PhotocardBox, id=box_id)
                box_name = box.name

                owned_cards = UserPhotocard.objects.filter(photocard__box=box).count()
                if owned_cards > 0:
                    box.is_active = False
                    box.save()
                    messages.error(request, f"⚠️ La caja «{box_name}» no se puede eliminar porque los usuarios ya tienen {owned_cards} cartas en sus álbumes. La caja fue PAUSADA.")
                else:
                    box.cards.all().delete()
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
                raw_image = request.FILES.get('image')

                if not raw_image or not name or not box_id:
                    messages.error(request, "Debes adjuntar el archivo de Canva, asignar un nombre y una caja.")
                else:
                    box_obj = get_object_or_404(PhotocardBox, id=box_id)
                    optimized_img = optimize_uploaded_image(raw_image)
                    
                    Photocard.objects.create(
                        box=box_obj,
                        idol_name=idol_name or "K-Pop Idol",
                        name=name,
                        rarity=rarity,
                        image=optimized_img,
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
                    card.image = optimize_uploaded_image(request.FILES['image'])
                card.save()
                messages.success(request, f"💾 Photocard «{card.name}» actualizada.")

            elif action == 'delete_card':
                card_id = request.POST.get('card_id')
                card = get_object_or_404(Photocard, id=card_id)
                c_name = card.name
                card.delete()
                messages.warning(request, f"🗑️ Photocard «{c_name}» eliminada.")

            elif action == 'save_upcoming_box':
                title = request.POST.get('upcoming_title', '').strip()
                date = request.POST.get('upcoming_date', '').strip()
                desc = request.POST.get('upcoming_desc', '').strip()
                is_active = request.POST.get('upcoming_active') == '1'

                KingdomSetting.set_val('upcoming_box_title', title)
                KingdomSetting.set_val('upcoming_box_date', date)
                KingdomSetting.set_val('upcoming_box_desc', desc)
                KingdomSetting.set_val('upcoming_box_active', 'true' if is_active else 'false')

                if 'upcoming_image' in request.FILES:
                    file_obj = optimize_uploaded_image(request.FILES['upcoming_image'])
                    saved_path = default_storage.save(f'photocard_boxes/upcoming_{file_obj.name}', file_obj)
                    image_url = default_storage.url(saved_path)
                    KingdomSetting.set_val('upcoming_box_image', image_url)

                messages.success(request, "📢 ¡Anuncio de Próximo Lanzamiento guardado con éxito!")

        except Exception as e:
            err_str = str(e)
            if "File size too large" in err_str:
                messages.error(request, "⚠️ La imagen supera el límite de carga permitido (10 MB). Por favor comprímela antes de subir.")
            else:
                messages.error(request, f"⚠️ Error al procesar archivo: {err_str}")

        return redirect(f'/idols/photocards/admin/?tg_id={tg_id}')

    boxes = PhotocardBox.objects.all().prefetch_related('cards')
    all_idols = IdolProfile.objects.all().order_by('stage_name')
    all_cards = Photocard.objects.all().select_related('box').order_by('-created_at')

    upcoming_active = KingdomSetting.get_val('upcoming_box_active', 'false') == 'true'
    upcoming_data = {
        'is_active': upcoming_active,
        'title': KingdomSetting.get_val('upcoming_box_title', ''),
        'release_date': KingdomSetting.get_val('upcoming_box_date', ''),
        'description': KingdomSetting.get_val('upcoming_box_desc', ''),
        'image_url': KingdomSetting.get_val('upcoming_box_image', '')
    }

    return render(request, 'idols/admin_photocards.html', {
        'tg_id': tg_id,
        'boxes': boxes,
        'all_idols': all_idols,
        'all_cards': all_cards,
        'upcoming': upcoming_data,
    })


def photocards_market(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

    market_cards = list(UserPhotocard.objects.filter(
        is_for_sale=True
    ).exclude(telegram_user_id=tg_id).select_related('photocard', 'photocard__idol', 'photocard__box').order_by('-obtained_at'))
    
    # 🌟 Cruzar con el inventario del usuario para saber si ya la tiene
    user_pcs = UserPhotocard.objects.filter(telegram_user_id=tg_id)
    user_card_counts = Counter(user_pcs.values_list('photocard_id', flat=True))
    for mc in market_cards:
        mc.already_owned = (mc.photocard_id in user_card_counts)
        mc.owned_qty = user_card_counts.get(mc.photocard_id, 0)

    my_sales = UserPhotocard.objects.filter(
        telegram_user_id=tg_id,
        is_for_sale=True
    ).select_related('photocard')

    received_trades = PhotocardTrade.objects.filter(
        Q(receiver_telegram_id=tg_id) | Q(receiver_telegram_id=0),
        status='pending'
    ).exclude(sender_telegram_id=tg_id).select_related('sender_card__photocard', 'receiver_card__photocard').order_by('-created_at')

    sent_trades = PhotocardTrade.objects.filter(
        sender_telegram_id=tg_id,
        status='pending'
    ).select_related('sender_card__photocard', 'receiver_card__photocard').order_by('-created_at')

    return render(request, 'idols/photocards_market.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'market_cards': market_cards,
        'my_sales': my_sales,
        'received_trades': received_trades,
        'sent_trades': sent_trades,
    })


def photocard_sell_action(request, user_card_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        user_card = get_object_or_404(UserPhotocard, id=user_card_id, telegram_user_id=tg_id)
        mode = request.POST.get('mode', 'list')

        if mode == 'list':
            try:
                price = int(request.POST.get('price', 50))
                if price < 20:
                    messages.error(request, "El precio mínimo de venta en el Mercado es de 20 🪙.")
                else:
                    user_card.is_for_sale = True
                    user_card.sale_price = price
                    user_card.save()
                    messages.success(request, f"🏷️ «{user_card.photocard.name}» publicada en el Mercado por {price} 🪙.")
            except ValueError:
                messages.error(request, "Precio no válido.")
        elif mode == 'cancel':
            user_card.is_for_sale = False
            user_card.sale_price = 0
            user_card.save()
            messages.info(request, f"Venta de «{user_card.photocard.name}» cancelada. Regresó a tu Álbum.")

    return redirect('/idols/photocards/album/')


def photocard_buy_action(request, user_card_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        buyer_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)

        with transaction.atomic():
            user_card = UserPhotocard.objects.select_for_update().filter(id=user_card_id, is_for_sale=True).first()
            if not user_card:
                messages.error(request, "Esta carta ya ha sido adquirida por otro noble o retirada del mercado.")
                return redirect('/idols/photocards/market/')

            if user_card.telegram_user_id == tg_id:
                messages.info(request, "No puedes comprar tu propia carta.")
                return redirect('/idols/photocards/market/')

            price = user_card.sale_price or 50
            if buyer_wallet.balance < price:
                messages.error(request, f"No tienes suficiente oro ({price} 🪙 necesarios).")
                return redirect('/idols/photocards/market/')

            buyer_wallet.remove_funds(price)
            vendedor_id = user_card.telegram_user_id
            
            from economy.models import UserInventoryItem
            used_free_tax = UserInventoryItem.consume_item(vendedor_id, 'free_market')
            
            fee = 0 if used_free_tax else int(price * 0.10)
            neto_vendedor = price - fee

            seller_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=vendedor_id)
            seller_wallet.add_funds(neto_vendedor)

            carta_nombre = user_card.photocard.name

            user_card.telegram_user_id = tg_id
            user_card.is_for_sale = False
            user_card.sale_price = 0
            user_card.save()

            PhotocardTrade.objects.filter(sender_card=user_card, status='pending').update(status='cancelled')
            PhotocardTrade.objects.filter(receiver_card=user_card, status='pending').update(status='cancelled')

            grant_user_xp(request, tg_id, 10, reason="Compra en Mercado")
            grant_user_xp(None, vendedor_id, 15, reason="Venta de Photocard")

            send_telegram_msg(
                chat_id=vendedor_id,
                text=(
                    f"🏷️ <b>¡Vendiste una Photocard en el Mercado!</b>\n\n"
                    f"🎴 <b>Carta:</b> {carta_nombre}\n"
                    f"🪙 <b>Precio:</b> {price} 🪙\n"
                    f"💰 <b>Ganancia neta recibida:</b> <b>+{neto_vendedor} 🪙</b> en tu Bóveda."
                ),
                button_text="🪙 Ver Mi Bóveda",
                button_url=f"https://kingdom-pleasure-app.onrender.com/economy/wallet/?tg_id={vendedor_id}"
            )

        messages.success(request, f"🎉 ¡Compraste «{carta_nombre}» por {price} 🪙! Ya está en tu Álbum.")
        return redirect(f'/idols/photocards/market/?tg_id={tg_id}')

    return redirect('/idols/photocards/market/')


# ==========================================
# EL CALDERO REAL: FUSIÓN INTELIGENTE
# ==========================================

def photocard_fusion(request):
    tg_id = resolve_safe_tg(request)
    if not tg_id:
        return redirect('/')

    wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    profile, _ = UserProfile.objects.get_or_create(telegram_user_id=tg_id)
    pet = Pet.objects.filter(telegram_user_id=tg_id).first()

    RECIPES = {
        'common':    {'required_count': 4, 'cost': 35,  'source_rarity': 'common',    'target_rarity': 'rare',      'luck_target': 'epic',      'luck_chance': 0.12},
        'rare':      {'required_count': 3, 'cost': 75,  'source_rarity': 'rare',      'target_rarity': 'epic',      'luck_target': 'legendary', 'luck_chance': 0.15},
        'epic':      {'required_count': 3, 'cost': 150, 'source_rarity': 'epic',      'target_rarity': 'epic',      'luck_target': 'legendary', 'luck_chance': 0.25},
        'legendary': {'required_count': 2, 'cost': 200, 'source_rarity': 'legendary', 'target_rarity': 'legendary', 'luck_target': 'legendary', 'luck_chance': 0.0},
    }

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        tier = request.POST.get('tier', 'common')
        raw_card_ids = request.POST.getlist('card_ids')

        recipe = RECIPES.get(tier)
        if not recipe:
            err = "Receta de fusión no válida."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

        try:
            card_ids = [int(cid) for cid in raw_card_ids if str(cid).isdigit()]
        except ValueError:
            card_ids = []

        req_single = recipe['required_count']
        if len(card_ids) == 0 or len(card_ids) % req_single != 0:
            err = f"Debes seleccionar cartas en múltiplos de {req_single} para esta transmutación."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

        batch_count = len(card_ids) // req_single
        total_cost = recipe['cost'] * batch_count

        if wallet.balance < total_cost:
            err = f"No tienes suficiente oro en tu Bóveda ({total_cost} 🪙 necesarios para {batch_count} transmutación{'es' if batch_count > 1 else ''})."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

        target_rarity = recipe['target_rarity']
        target_pool_exists = Photocard.objects.filter(rarity=target_rarity).exists()
        luck_pool_exists = Photocard.objects.filter(rarity=recipe['luck_target']).exists()

        if not target_pool_exists and not luck_pool_exists:
            err = f"⚠️ La Corona aún no ha forjado Photocards de rareza {target_rarity.upper()}."
            if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

        with transaction.atomic():
            selected_cards = list(UserPhotocard.objects.select_for_update().filter(
                id__in=card_ids,
                telegram_user_id=tg_id,
                is_for_sale=False,
                photocard__rarity=recipe['source_rarity']
            ).select_related('photocard'))

            if len(selected_cards) != len(card_ids):
                err = "Algunas cartas seleccionadas ya no están disponibles, están en venta o no coinciden en rareza."
                if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                messages.error(request, err)
                return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

            # Proteger siempre al menos 1 copia de cada carta en el álbum
            sacrificed_counts = Counter(c.photocard_id for c in selected_cards)
            for pid, count in sacrificed_counts.items():
                total_owned = UserPhotocard.objects.filter(
                    telegram_user_id=tg_id,
                    photocard_id=pid
                ).count()
                if (total_owned - count) < 1:
                    err = "⚠️ No puedes fundir tu única copia de una Photocard. La Corona protege tu Álbum."
                    if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
                    messages.error(request, err)
                    return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

            wallet.remove_funds(total_cost)

            consumed_ids = [c.id for c in selected_cards]
            PhotocardTrade.objects.filter(sender_card_id__in=consumed_ids, status='pending').update(status='cancelled')
            PhotocardTrade.objects.filter(receiver_card_id__in=consumed_ids, status='pending').update(status='cancelled')
            UserPhotocard.objects.filter(id__in=consumed_ids).delete()

            currently_owned_card_ids = set(
                UserPhotocard.objects.filter(telegram_user_id=tg_id)
                .values_list('photocard_id', flat=True)
            )

            luck_prob_base = recipe['luck_chance']
            if pet and pet.species == 'rabbit':
                rabbit_bonus = {1: 0.03, 2: 0.06, 3: 0.10}.get(pet.evolution_stage_number, 0.03)
                luck_prob_base += rabbit_bonus

            forged_cards = []
            xp_map = {'rare': 15, 'epic': 30, 'legendary': 60}
            total_earned_xp = 0

            for _ in range(batch_count):
                roll = random.random()
                is_lucky_jump = False

                if roll < luck_prob_base and luck_pool_exists:
                    awarded_rarity = recipe['luck_target']
                    is_lucky_jump = True
                elif target_pool_exists:
                    awarded_rarity = recipe['target_rarity']
                else:
                    awarded_rarity = recipe['source_rarity']

                pool = list(Photocard.objects.filter(rarity=awarded_rarity))
                if not pool:
                    pool = list(Photocard.objects.filter(rarity=recipe['source_rarity']))
                    if not pool:
                        pool = list(Photocard.objects.all())

                unowned_in_pool = [c for c in pool if c.id not in currently_owned_card_ids]

                if unowned_in_pool:
                    new_card = random.choice(unowned_in_pool)
                    is_new_discovery = True
                else:
                    new_card = random.choice(pool)
                    is_new_discovery = False

                currently_owned_card_ids.add(new_card.id)
                new_user_card = UserPhotocard.objects.create(telegram_user_id=tg_id, photocard=new_card)

                earned_xp = xp_map.get(new_card.rarity, 20)
                total_earned_xp += earned_xp
                grant_user_xp(request, tg_id, earned_xp, reason="Alquimia de Photocards")

                forged_cards.append({
                    'id': new_user_card.id,
                    'name': new_card.name,
                    'idol_name': new_card.display_idol_name,
                    'rarity': new_card.rarity,
                    'rarity_display': new_card.get_rarity_display(),
                    'color': new_card.get_color_hex(),
                    'image_url': new_card.image.url if new_card.image else '',
                    'is_new': is_new_discovery,
                    'is_lucky': is_lucky_jump
                })

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'batch_count': batch_count,
                    'nuevo_saldo': wallet.balance,
                    'total_xp': total_earned_xp,
                    'cards': forged_cards,
                    'card': forged_cards[0],
                    'is_new': any(c['is_new'] for c in forged_cards),
                    'is_lucky': any(c['is_lucky'] for c in forged_cards)
                })

            messages.success(request, f"✨ ¡Alquimia completada! Obtuviste {len(forged_cards)} nuevas photocards.")
            return redirect(f'/idols/photocards/fusion/?tg_id={tg_id}')

    all_user_cards = UserPhotocard.objects.filter(
        telegram_user_id=tg_id,
        is_for_sale=False
    ).select_related('photocard').order_by('photocard_id', 'id')

    seen_photocard_ids = set()
    duplicate_cards = []

    for uc in all_user_cards:
        if uc.photocard_id not in seen_photocard_ids:
            seen_photocard_ids.add(uc.photocard_id)
        else:
            duplicate_cards.append(uc)

    commons     = [c for c in duplicate_cards if c.photocard.rarity == 'common']
    rares       = [c for c in duplicate_cards if c.photocard.rarity == 'rare']
    epics       = [c for c in duplicate_cards if c.photocard.rarity == 'epic']
    legendaries = [c for c in duplicate_cards if c.photocard.rarity == 'legendary']

    return render(request, 'idols/photocard_fusion.html', {
        'tg_id': tg_id,
        'wallet': wallet,
        'profile': profile,
        'pet': pet,
        'commons': commons,
        'rares': rares,
        'epics': epics,
        'legendaries': legendaries,
        'total_duplicates': len(duplicate_cards),
    })


# ==========================================
# INTERCAMBIOS P2P BLINDADOS
# ==========================================

def create_trade_offer(request, user_card_id):
    if request.method == 'POST':
        tg_id = resolve_safe_tg(request)
        sender_card = get_object_or_404(UserPhotocard, id=user_card_id, telegram_user_id=tg_id, is_for_sale=False)
        
        target_raw = request.POST.get('target_user', '').strip()
        receiver_id = None
        receiver_name = 'Noble'

        if target_raw == 'open':
            receiver_id = 0
            receiver_name = 'Cualquier Miembro del Reino'
        elif target_raw.isdigit():
            receiver_id = int(target_raw)
            p = UserProfile.objects.filter(telegram_user_id=receiver_id).first()
            if p and p.username: receiver_name = p.username
        else:
            clean_at = target_raw if target_raw.startswith('@') else f"@{target_raw}"
            p = UserProfile.objects.filter(username__iexact=clean_at).first()
            if p:
                receiver_id = p.telegram_user_id
                receiver_name = p.username

        if receiver_id is None or receiver_id == tg_id:
            messages.error(request, "Debes seleccionar a un destinatario válido.")
            return redirect('/idols/photocards/album/')

        sender_profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
        s_name = sender_profile.username if (sender_profile and sender_profile.username) else f"Noble_{tg_id}"

        PhotocardTrade.objects.filter(sender_card=sender_card, status='pending').update(status='cancelled')

        trade = PhotocardTrade.objects.create(
            sender_telegram_id=tg_id,
            sender_username=s_name,
            sender_card=sender_card,
            receiver_telegram_id=receiver_id,
            receiver_username=receiver_name,
            status='pending'
        )

        if receiver_id != 0:
            send_telegram_msg(
                chat_id=receiver_id,
                text=(
                    f"🤝 <b>¡Nueva Oferta de Intercambio de Photocards!</b>\n\n"
                    f"👤 <b>De:</b> {s_name}\n"
                    f"🎴 <b>Te ofrece:</b> <i>«{sender_card.photocard.name}»</i> ({sender_card.photocard.get_rarity_display()})\n\n"
                    f"Ingresa a tu Mercado para revisar y aceptar el intercambio."
                ),
                button_text="🤝 Revisar Oferta",
                button_url=f"https://kingdom-pleasure-app.onrender.com/idols/photocards/market/?tg_id={receiver_id}"
            )
            messages.success(request, f"🤝 Propuesta enviada directamente a {receiver_name}.")
        else:
            messages.success(request, "📢 ¡Tu carta ha sido publicada en el Tablón de Intercambios del Mercado para cualquiera!")

        return redirect('/idols/photocards/market/')

    return redirect('/idols/photocards/album/')


def handle_trade_offer(request, trade_id, action):
    tg_id = resolve_safe_tg(request)
    trade = get_object_or_404(PhotocardTrade, id=trade_id, status='pending')

    is_authorized = (trade.receiver_telegram_id == tg_id) or (trade.receiver_telegram_id == 0 and trade.sender_telegram_id != tg_id)

    if action == 'accept' and is_authorized:
        return_card_id = request.POST.get('return_card_id') or request.GET.get('return_card_id')
        
        with transaction.atomic():
            sender_card = UserPhotocard.objects.select_for_update().filter(id=trade.sender_card_id).first()
            
            if not sender_card or sender_card.telegram_user_id != trade.sender_telegram_id or sender_card.is_for_sale:
                trade.status = 'cancelled'
                trade.save()
                messages.error(request, "⚠️ El intercambio no se pudo completar: el emisor ya no posee esta carta o la puso a la venta.")
                return redirect('/idols/photocards/market/')

            receiver_card = None
            if return_card_id and str(return_card_id).isdigit():
                receiver_card = UserPhotocard.objects.select_for_update().filter(
                    id=int(return_card_id),
                    telegram_user_id=tg_id,
                    is_for_sale=False
                ).first()

            if not receiver_card:
                messages.error(request, "⚠️ Debes seleccionar una carta válida de tu colección para completar el intercambio recíproco.")
                return redirect('/idols/photocards/market/')

            sender_card.telegram_user_id = tg_id
            sender_card.is_for_sale = False
            sender_card.sale_price = 0
            sender_card.save()

            receiver_card.telegram_user_id = trade.sender_telegram_id
            receiver_card.is_for_sale = False
            receiver_card.sale_price = 0
            receiver_card.save()
            trade.receiver_card = receiver_card

            trade.receiver_telegram_id = tg_id
            receiver_profile = UserProfile.objects.filter(telegram_user_id=tg_id).first()
            if receiver_profile and receiver_profile.username:
                trade.receiver_username = receiver_profile.username

            trade.status = 'accepted'
            trade.save()

            send_telegram_msg(
                chat_id=trade.sender_telegram_id,
                text=(
                    f"🎉 <b>¡Tu intercambio de Photocards fue aceptado!</b>\n\n"
                    f"👤 <b>Por:</b> {trade.receiver_username}\n"
                    f"🎴 <b>Entregaste:</b> «{sender_card.photocard.name}»\n" +
                    (f"🎴 <b>Recibiste a cambio:</b> «{receiver_card.photocard.name}»" if receiver_card else "")
                ),
                button_text="🎴 Ver Mi Álbum",
                button_url=f"https://kingdom-pleasure-app.onrender.com/idols/photocards/album/?tg_id={trade.sender_telegram_id}"
            )

            grant_user_xp(request, tg_id, 15, reason="Intercambio Exitoso")
            grant_user_xp(None, trade.sender_telegram_id, 15, reason="Intercambio Exitoso")

        messages.success(request, f"🎉 ¡Intercambio completado! «{sender_card.photocard.name}» ya está en tu Álbum.")

    elif action == 'reject' and is_authorized:
        trade.status = 'rejected'
        trade.save()
        send_telegram_msg(
            chat_id=trade.sender_telegram_id,
            text=f"⚠️ Tu propuesta de intercambio de «{trade.sender_card.photocard.name}» fue rechazada."
        )
        messages.info(request, "Propuesta rechazada.")

    elif action == 'cancel' and trade.sender_telegram_id == tg_id:
        trade.status = 'cancelled'
        trade.save()
        messages.info(request, "Propuesta de intercambio cancelada.")

    return redirect('/idols/photocards/market/')

    tg_id = resolve_safe_tg(request)
    is_admin = check_is_staff_or_admin(tg_id)
    if not is_admin:
        messages.error(request, "Solo los administradores pueden gestionar Photocards.")
        return redirect('/idols/photocards/')

    target_tab = 'subir'

    if request.method == 'POST':
        action = request.POST.get('action')
        target_tab = request.POST.get('target_tab', 'subir')
        try:
            if action == 'create_box':
                target_tab = 'cajas'
                name = request.POST.get('name', '').strip()
                description = request.POST.get('description', '').strip()
                price = int(request.POST.get('price', 120))
                
                # Permite archivo de galería O enlace directo
                cover_file = request.FILES.get('cover_image')
                cover_url = request.POST.get('cover_url', '').strip()
                if not cover_file and cover_url:
                    cover_file = download_image_from_url(cover_url, default_filename=f"box_{name[:12]}.webp")
                
                cover_image = optimize_uploaded_image(cover_file)
                if name:
                    PhotocardBox.objects.create(name=name, description=description, price=price, cover_image=cover_image)
                    messages.success(request, f"✨ Caja «{name}» creada exitosamente.")

            elif action == 'edit_box':
                target_tab = 'cajas'
                box_id = request.POST.get('box_id')
                box = get_object_or_404(PhotocardBox, id=box_id)
                box.name = request.POST.get('name', box.name).strip()
                box.description = request.POST.get('description', box.description).strip()
                box.price = int(request.POST.get('price', box.price))
                
                cover_file = request.FILES.get('cover_image')
                cover_url = request.POST.get('cover_url', '').strip()
                if not cover_file and cover_url:
                    cover_file = download_image_from_url(cover_url, default_filename=f"box_{box.id}.webp")
                
                if cover_file:
                    box.cover_image = optimize_uploaded_image(cover_file)
                box.save()
                messages.success(request, f"💾 Caja «{box.name}» actualizada.")

            elif action == 'delete_box':
                target_tab = 'cajas'
                box_id = request.POST.get('box_id')
                box = get_object_or_404(PhotocardBox, id=box_id)
                box_name = box.name
                owned_cards = UserPhotocard.objects.filter(photocard__box=box).count()
                if owned_cards > 0:
                    box.is_active = False
                    box.save()
                    messages.error(request, f"⚠️ La caja «{box_name}» no se puede eliminar porque los usuarios ya tienen {owned_cards} cartas en sus álbumes. La caja fue PAUSADA.")
                else:
                    box.cards.all().delete()
                    box.delete()
                    messages.warning(request, f"🗑️ Caja «{box_name}» eliminada.")

            elif action == 'toggle_box':
                target_tab = 'cajas'
                box_id = request.POST.get('box_id')
                box = get_object_or_404(PhotocardBox, id=box_id)
                box.is_active = not box.is_active
                box.save()
                estado = "Activada" if box.is_active else "Pausada"
                messages.info(request, f"Caja {box.name} {estado}.")

            elif action == 'upload_card':
                target_tab = 'subir'
                box_id = request.POST.get('box_id')
                idol_name = request.POST.get('idol_name', '').strip()
                name = request.POST.get('name', '').strip()
                rarity = request.POST.get('rarity', 'common')
                
                raw_image = request.FILES.get('image')
                card_url = request.POST.get('card_url', '').strip()
                if not raw_image and card_url:
                    raw_image = download_image_from_url(card_url, default_filename=f"card_{name[:12]}.webp")
                
                if not raw_image or not name or not box_id:
                    messages.error(request, "Debes adjuntar el archivo de Canva (o su enlace), asignar un nombre y una caja.")
                else:
                    box_obj = get_object_or_404(PhotocardBox, id=box_id)
                    optimized_img = optimize_uploaded_image(raw_image)
                    
                    Photocard.objects.create(
                        box=box_obj,
                        idol_name=idol_name or "K-Pop Idol",
                        name=name,
                        rarity=rarity,
                        image=optimized_img,
                        created_by_tg_id=tg_id
                    )
                    messages.success(request, f"🎴 Photocard «{name}» ({idol_name}) subida con éxito.")

            elif action == 'edit_card':
                target_tab = 'cartas'
                card_id = request.POST.get('card_id')
                card = get_object_or_404(Photocard, id=card_id)
                card.box_id = request.POST.get('box_id', card.box_id)
                card.name = request.POST.get('name', card.name).strip()
                card.idol_name = request.POST.get('idol_name', card.idol_name).strip()
                card.rarity = request.POST.get('rarity', card.rarity)
                
                new_img = request.FILES.get('image')
                new_url = request.POST.get('card_url', '').strip()
                if not new_img and new_url:
                    new_img = download_image_from_url(new_url, default_filename=f"card_{card.id}.webp")
                if new_img:
                    card.image = optimize_uploaded_image(new_img)
                card.save()
                messages.success(request, f"💾 Photocard «{card.name}» actualizada.")

            elif action == 'delete_card':
                target_tab = 'cartas'
                card_id = request.POST.get('card_id')
                card = get_object_or_404(Photocard, id=card_id)
                card_name = card.name
                card.delete()
                messages.warning(request, f"🗑️ Photocard «{card_name}» eliminada.")

            elif action == 'save_upcoming_box':
                target_tab = 'proxima'
                title = request.POST.get('upcoming_title', '').strip()
                date = request.POST.get('upcoming_date', '').strip()
                desc = request.POST.get('upcoming_desc', '').strip()
                is_active = request.POST.get('upcoming_active') == '1'

                KingdomSetting.set_val('upcoming_box_title', title)
                KingdomSetting.set_val('upcoming_box_date', date)
                KingdomSetting.set_val('upcoming_box_desc', desc)
                KingdomSetting.set_val('upcoming_box_active', 'true' if is_active else 'false')

                file_obj = request.FILES.get('upcoming_image')
                url_obj = request.POST.get('upcoming_image_url', '').strip()
                if not file_obj and url_obj:
                    file_obj = download_image_from_url(url_obj, default_filename='upcoming.webp')

                if file_obj:
                    file_opt = optimize_uploaded_image(file_obj)
                    saved_path = default_storage.save(f'photocard_boxes/upcoming_{file_opt.name}', file_opt)
                    image_url = default_storage.url(saved_path)
                    KingdomSetting.set_val('upcoming_box_image', image_url)

                messages.success(request, "📢 ¡Anuncio de Próximo Lanzamiento guardado con éxito!")

        except Exception as e:
            err_str = str(e)
            if "File size too large" in err_str:
                messages.error(request, "⚠️ La imagen supera el límite de carga permitido (10 MB). Por favor comprímela antes de subir.")
            else:
                messages.error(request, f"⚠️ Error al procesar archivo: {err_str}")

        return redirect(f'/idols/photocards/admin/?tg_id={tg_id}&tab={target_tab}')

    boxes = PhotocardBox.objects.all().prefetch_related('cards')
    all_idols = IdolProfile.objects.all().order_by('stage_name')
    all_cards = Photocard.objects.all().select_related('box').order_by('-created_at')

    upcoming_active = KingdomSetting.get_val('upcoming_box_active', 'false') == 'true'
    upcoming_data = {
        'is_active': upcoming_active,
        'title': KingdomSetting.get_val('upcoming_box_title', ''),
        'release_date': KingdomSetting.get_val('upcoming_box_date', ''),
        'description': KingdomSetting.get_val('upcoming_box_desc', ''),
        'image_url': KingdomSetting.get_val('upcoming_box_image', '')
    }

    current_tab = request.GET.get('tab', 'subir')

    return render(request, 'idols/admin_photocards.html', {
        'boxes': boxes,
        'all_idols': all_idols,
        'all_cards': all_cards,
        'upcoming': upcoming_data,
        'current_tab': current_tab,
        'tg_id': tg_id
    })



# ==============================================================================
# 🎭 MÓDULO DE DISPONIBILIDAD & SOLICITUDES DE ROL
# ==============================================================================
def toggle_roleplay_status(request, idol_id):
    """Permite a la idol encender/apagar su anuncio de disponibilidad de rol."""
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id)
    is_admin = check_is_staff_or_admin(tg_id)
    if not (tg_id and (tg_id == idol.telegram_user_id or is_admin)):
        messages.error(request, "Acceso exclusivo para la dueña de la Musa.")
        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')
    
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'
        is_open = request.POST.get('is_roleplay_open') in ['1', 'true', 'on', True]
        notice = request.POST.get('roleplay_notice', '').strip()
        try:
            price = max(50, int(request.POST.get('roleplay_price', 100)))
        except (ValueError, TypeError):
            price = 100
        
        idol.is_roleplay_open = is_open
        if notice:
            idol.roleplay_notice = notice[:160]
        idol.roleplay_price = price
        if is_open:
            idol.status = 'online'
        idol.save(update_fields=['is_roleplay_open', 'roleplay_notice', 'roleplay_price', 'status'])
        
        status_label = "🟢 DISPONIBLE PARA ROL" if is_open else "🌙 Modo Descanso / Pausado"
        msg = f"✨ Tu cartel en vivo ha sido actualizado a: {status_label}."
        if is_ajax:
            return JsonResponse({'success': True, 'is_open': is_open, 'message': msg})
        messages.success(request, msg)
    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')


def request_roleplay_session(request, idol_id):
    """Permite al cliente solicitar una sesión de rol depositando oro en custodia."""
    if request.method != 'POST':
        return redirect(f'/idols/{idol_id}/')
    
    tg_id = resolve_safe_tg(request)
    idol = get_object_or_404(IdolProfile, id=idol_id)
    profile = UserProfile.objects.filter(telegram_user_id=tg_id).first() if tg_id else None
    client_username = request.POST.get('client_username') or (profile.username if profile else 'Noble')
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'

    if tg_id and tg_id == idol.telegram_user_id:
        err = "No puedes solicitarte una sesión de rol a ti misma."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

    theme = request.POST.get('theme', '').strip()
    details = request.POST.get('details', '').strip()
    try:
        bounty = int(request.POST.get('bounty', idol.roleplay_price))
    except (ValueError, TypeError):
        bounty = idol.roleplay_price

    if not theme:
        err = "Debes indicar una temática o idea para la sesión de rol."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

    min_price = idol.roleplay_price or 100
    if bounty < min_price:
        err = f"La ofrenda mínima para esta Musa es de {min_price} 🪙."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

    from economy.models import Wallet
    client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=tg_id)
    if client_wallet.balance < bounty:
        err = f"Oro insuficiente ({client_wallet.balance}/{bounty} 🪙) para formalizar la petición."
        if is_ajax: return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
        return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')

    with transaction.atomic():
        client_wallet.remove_funds(bounty)
        session_req = RoleSessionRequest.objects.create(
            idol=idol,
            client_telegram_id=tg_id,
            client_username=client_username,
            theme=theme,
            details=details,
            bounty=bounty,
            status='pending'
        )

    # Enviar notificación inmediata a la idol por Telegram
    notif_text = (
        f"🎭 <b>¡NUEVA SOLICITUD DE ROL PARA {idol.stage_name}!</b>\n\n"
        f"👤 <b>Cliente:</b> @{client_username}\n"
        f"📜 <b>Temática:</b> {theme}\n"
        f"🪙 <b>Ofrenda en custodia:</b> {bounty} 🪙\n\n"
        f"<i>Abre tu perfil en el bot para Aceptar el rol y comenzar el chat.</i>"
    )
    send_telegram_msg(chat_id=idol.telegram_user_id, text=notif_text)

    msg = f"💌 ¡Petición de rol enviada a {idol.stage_name}! Tu oro ({bounty} 🪙) quedó en custodia hasta que se complete la sesión."
    if is_ajax:
        return JsonResponse({'success': True, 'message': msg, 'request_id': session_req.id})
    messages.success(request, msg)
    return redirect(f'/idols/{idol_id}/?tg_id={tg_id}')


def handle_roleplay_request(request, request_id, action):
    """Permite a la idol aceptar, completar o rechazar la solicitud de rol."""
    tg_id = resolve_safe_tg(request)
    session_req = get_object_or_404(RoleSessionRequest, id=request_id)
    idol = session_req.idol
    is_owner = bool(tg_id and tg_id == idol.telegram_user_id)
    is_client = bool(tg_id and tg_id == session_req.client_telegram_id)
    is_admin = check_is_staff_or_admin(tg_id)

    if not (is_owner or is_client or is_admin):
        messages.error(request, "Acceso no autorizado.")
        return redirect(f'/idols/{idol.id}/?tg_id={tg_id}')

    from economy.models import Wallet

    if action == 'accept' and (is_owner or is_admin):
        session_req.status = 'accepted'
        session_req.save(update_fields=['status', 'updated_at'])
        client_msg = f"✨ <b>¡{idol.stage_name} ha ACEPTADO tu solicitud de rol!</b>\nTemática: {session_req.theme}\nTe contactará en breve por Telegram."
        send_telegram_msg(chat_id=session_req.client_telegram_id, text=client_msg)
        messages.success(request, f"¡Petición aceptada! Ya puedes abrir chat con @{session_req.client_username}.")

    elif action == 'complete' and (is_owner or is_admin):
        with transaction.atomic():
            session_req.status = 'completed'
            session_req.save(update_fields=['status', 'updated_at'])
            idol_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=idol.telegram_user_id)
            idol_wallet.add_funds(session_req.bounty)
            idol.services_done += 1
            idol.save(update_fields=['services_done'])
        
        grant_user_xp(request, idol.telegram_user_id, 25, reason=f"Sesión de Rol con {idol.stage_name}")
        grant_user_xp(None, session_req.client_telegram_id, 15, reason=f"Rol con {idol.stage_name}")

        done_msg = f"👑 <b>¡Sesión de rol con {idol.stage_name} completada!</b>\nSe han transferido {session_req.bounty} 🪙 a la Musa."
        send_telegram_msg(chat_id=session_req.client_telegram_id, text=done_msg)
        messages.success(request, f"🎉 ¡Rol completado! Se han depositado {session_req.bounty} 🪙 en tu bóveda.")

    elif action == 'reject' and (is_owner or is_admin):
        with transaction.atomic():
            session_req.status = 'rejected'
            session_req.save(update_fields=['status', 'updated_at'])
            client_wallet, _ = Wallet.objects.get_or_create(telegram_user_id=session_req.client_telegram_id)
            client_wallet.add_funds(session_req.bounty)

        rej_msg = f"ℹ️ <b>Tu solicitud de rol para {idol.stage_name} no pudo ser atendida.</b>\nTus {session_req.bounty} 🪙 fueron devueltos a tu bóveda."
        send_telegram_msg(chat_id=session_req.client_telegram_id, text=rej_msg)
        messages.info(request, f"Petición rechazada. Fondos reembolsados a @{session_req.client_username}.")

    return redirect(f'/idols/{idol.id}/?tg_id={tg_id}')

