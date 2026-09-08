from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import IdolProfile

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