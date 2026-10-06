# core/utils.py
from core.models import UserProfile
from economy.models import Wallet
from django.contrib import messages
from django.db import transaction

def grant_user_xp(request, tg_id, xp_amount, reason=""):
    if not tg_id or str(tg_id).strip() in ['', 'None', 'undefined', 'null']:
        return
        
    try:
        clean_id = int(tg_id)
        if xp_amount <= 0:
            return

        # BUFF BÚHO CRONOS: +15% / +30% / +50% EXP nobiliaria
        try:
            from pets.models import Pet
            pet = Pet.objects.filter(telegram_user_id=clean_id).first()
            if pet and pet.species == 'owl':
                owl_rates = {1: 1.15, 2: 1.30, 3: 1.50}
                xp_amount = int(round(xp_amount * owl_rates.get(pet.evolution_stage_number, 1.15)))
        except Exception:
            pass

        with transaction.atomic():
            profile, _ = UserProfile.objects.select_for_update().get_or_create(
                telegram_user_id=clean_id,
                defaults={'username': f'Noble {clean_id}'}
            )
            
            leveled_up, new_level, gold_reward = profile.add_xp(xp_amount)

            if leveled_up and gold_reward > 0:
                wallet, _ = Wallet.objects.select_for_update().get_or_create(telegram_user_id=clean_id)
                wallet.add_funds(gold_reward)
                
                if request:
                    titulo_rango = profile.get_rank_name()
                    messages.success(
                        request, 
                        f"🎉 ¡ASCENSO! Has alcanzado el Nivel {new_level} ({titulo_rango}). "
                        f"La Corona te premia con +{gold_reward} 🪙 de oro."
                    )
    except Exception:
        pass