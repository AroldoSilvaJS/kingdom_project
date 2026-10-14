from django.db import models
from django.utils import timezone
from datetime import timedelta

class Wallet(models.Model):
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    balance = models.IntegerField("Monedas de Oro", default=100)
    last_bonus_claim = models.DateTimeField("Último bono", null=True, blank=True)
    
    # 👑 PILAR 1: COFRE DEL MECENAS (RAKEBACK ACUMULATIVO DEL 8%)
    patron_vault = models.PositiveIntegerField("Cofre del Mecenas", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billetera"
        verbose_name_plural = "Billeteras"

    def __str__(self):
        return f"Wallet {self.telegram_user_id} - Saldo: {self.balance}"
    
    def add_funds(self, amount):
        self.balance += amount
        self.save()
        
    def remove_funds(self, amount):
        if self.balance >= amount:
            self.balance -= amount
            self.save()
            return True
        return False

    def accumulate_patron_vault(self, bet_amount):
        """Acumula automáticamente el 8% de cada apuesta en el Cofre del Mecenas."""
        rebate = max(1, int(round(bet_amount * 0.08)))
        self.patron_vault += rebate
        self.save(update_fields=['patron_vault'])
        return rebate

    def claim_patron_vault(self):
        """Transfiere el oro acumulado en el Cofre a su saldo disponible."""
        amount = self.patron_vault
        if amount > 0:
            self.balance += amount
            self.patron_vault = 0
            self.save(update_fields=['balance', 'patron_vault'])
            return amount
        return 0

    def get_cooldown_hours(self):
        try:
            from pets.models import Pet
            pet = Pet.objects.filter(telegram_user_id=self.telegram_user_id).first()
            if pet and pet.species == 'fox':
                stage = pet.evolution_stage_number
                if stage >= 3:
                    return 18
                elif stage == 2:
                    return 20
                return 22
        except Exception:
            pass
        return 24

    def can_claim_bonus(self):
        if not self.last_bonus_claim:
            return True
        hours = self.get_cooldown_hours()
        return timezone.now() >= self.last_bonus_claim + timedelta(hours=hours)
    
    def seconds_until_next_bonus(self):
        if self.can_claim_bonus():
            return 0
        hours = self.get_cooldown_hours()
        proximo_reclamo = self.last_bonus_claim + timedelta(hours=hours)
        restante = (proximo_reclamo - timezone.now()).total_seconds()
        return max(0, int(restante))


class UserInventoryItem(models.Model):
    telegram_user_id = models.BigIntegerField("ID del Usuario", db_index=True)
    item_code = models.CharField("Código de Ítem", max_length=50, db_index=True)
    quantity = models.PositiveIntegerField("Cantidad", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ítem de Inventario"
        verbose_name_plural = "Ítems de Inventario"
        unique_together = ('telegram_user_id', 'item_code')

    def __str__(self):
        return f"{self.telegram_user_id} - {self.item_code} (x{self.quantity})"

    @classmethod
    def add_item(cls, tg_id, item_code, qty=1):
        obj, created = cls.objects.get_or_create(
            telegram_user_id=tg_id, 
            item_code=item_code,
            defaults={'quantity': qty}
        )
        if not created:
            obj.quantity += qty
            obj.save(update_fields=['quantity', 'updated_at'])
        return obj

    @classmethod
    def consume_item(cls, tg_id, item_code, qty=1):
        obj = cls.objects.filter(telegram_user_id=tg_id, item_code=item_code).first()
        if obj and obj.quantity >= qty:
            obj.quantity -= qty
            if obj.quantity <= 0:
                obj.delete()
            else:
                obj.save(update_fields=['quantity', 'updated_at'])
            return True
        return False

    @classmethod
    def get_count(cls, tg_id, item_code):
        obj = cls.objects.filter(telegram_user_id=tg_id, item_code=item_code).first()
        return obj.quantity if obj else 0