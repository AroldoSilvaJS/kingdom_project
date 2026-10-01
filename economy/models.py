from django.db import models
from django.utils import timezone
from datetime import timedelta

class Wallet(models.Model):
    # Cada usuario solo debe tener una billetera asociada a su ID de Telegram
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    
    # Saldo del usuario (150 monedas de oro como regalo inicial)
    balance = models.IntegerField("Monedas de Oro", default=150)
    
    # Marca temporal del último bono diario reclamado
    last_bonus_claim = models.DateTimeField("Último bono", null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billetera"
        verbose_name_plural = "Billeteras"

    def __str__(self):
        return f"Wallet {self.telegram_user_id} - Saldo: {self.balance}"
    
    def add_funds(self, amount):
        """Suma oro a la billetera"""
        self.balance += amount
        self.save()
        
    def remove_funds(self, amount):
        """Resta oro verificando que no quede en saldo negativo"""
        if self.balance >= amount:
            self.balance -= amount
            self.save()
            return True
        return False

    # --- LÓGICA DE COOLDOWN DINÁMICA (BUFF DE MASCOTA: ZORRO) ---
    def get_cooldown_hours(self):
        """
        Si el usuario posee un Zorro Kitsune en su Santuario,
        el bono diario se recarga en 22 horas en vez de 24.
        """
        try:
            from pets.models import Pet
            pet = Pet.objects.filter(telegram_user_id=self.telegram_user_id).first()
            if pet and pet.species == 'fox':
                return 22
        except Exception:
            pass
        return 24

    def can_claim_bonus(self):
        """Verifica si ya transcurrieron las horas necesarias para volver a reclamar"""
        if not self.last_bonus_claim:
            return True # Primer reclamo siempre disponible
        hours = self.get_cooldown_hours()
        return timezone.now() >= self.last_bonus_claim + timedelta(hours=hours)
    
    def seconds_until_next_bonus(self):
        """Calcula los segundos exactos restantes para el temporizador en frontend"""
        if self.can_claim_bonus():
            return 0
        hours = self.get_cooldown_hours()
        proximo_reclamo = self.last_bonus_claim + timedelta(hours=hours)
        restante = (proximo_reclamo - timezone.now()).total_seconds()
        return max(0, int(restante))