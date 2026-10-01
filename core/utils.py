# core/utils.py
from core.models import UserProfile
from economy.models import Wallet
from django.contrib import messages
from django.db import transaction

def grant_user_xp(request, tg_id, xp_amount, reason=""):
    """
    Otorga EXP garantizada al noble o a la musa,
    controla la subida de nivel y entrega oro real a su Bóveda.
    """
    if not tg_id or str(tg_id).strip() in ['', 'None', 'undefined', 'null']:
        return
        
    try:
        clean_id = int(tg_id)
        if xp_amount <= 0:
            return

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