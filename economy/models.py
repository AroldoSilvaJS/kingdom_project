from django.db import models

class Wallet(models.Model):
    # Usamos unique=True porque cada usuario solo debe tener una billetera
    telegram_user_id = models.BigIntegerField(unique=True, db_index=True)
    
    # Saldo del usuario. Empezamos con 500 de oro como regalo inicial
    balance = models.IntegerField("Monedas de Oro", default=500)
    
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