from django.db import models
from django.utils import timezone
from datetime import timedelta

class Wallet(models.Model):
    # Usamos unique=True porque cada usuario solo debe tener una billetera
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    
    # Saldo del usuario. Empezamos con 500 de oro como regalo inicial
    balance = models.IntegerField("Monedas de Oro", default=500)
    
    # NUEVO CAMPO: Recuerda cuándo reclamó su último bono
    last_bonus_claim = models.DateTimeField("Último bono", null=True, blank=True)
    
    # Registro de cuándo se creó y actualizó
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Billetera"
        verbose_name_plural = "Billeteras"

    def __str__(self):
        return f"Wallet {self.telegram_user_id} - Saldo: {self.balance}"
    
    def add_funds(self, amount):
        """Método útil para sumar dinero fácilmente"""
        self.balance += amount
        self.save()
        
    def remove_funds(self, amount):
        """Método útil para restar dinero verificando que tenga saldo"""
        if self.balance >= amount:
            self.balance -= amount
            self.save()
            return True
        return False

    # NUEVA FUNCIÓN: Verifica matemáticamente si pasaron 24 horas
    def can_claim_bonus(self):
        if not self.last_bonus_claim:
            return True # Si nunca ha reclamado, puede hacerlo
        return timezone.now() >= self.last_bonus_claim + timedelta(hours=24)