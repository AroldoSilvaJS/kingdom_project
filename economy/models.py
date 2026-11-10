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

    # 🕛 RESET FIJO AL MEDIODÍA (12:00 PM HORA SERVIDOR / CHILE)
    def get_current_cycle_start(self):
        """Calcula el inicio del ciclo diario actual (12:00 PM)."""
        now = timezone.now().astimezone(timezone.get_current_timezone())
        if now.hour >= 12:
            return now.replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=12, minute=0, second=0, microsecond=0)

    def can_claim_bonus(self):
        """Permite girar una vez por ciclo diario (resetea cada día a las 12:00 PM)."""
        if not self.last_bonus_claim:
            return True
        cycle_start = self.get_current_cycle_start()
        return self.last_bonus_claim < cycle_start
    
    def seconds_until_next_bonus(self):
        """Segundos restantes hasta las próximas 12:00 PM."""
        if self.can_claim_bonus():
            return 0
        now = timezone.now().astimezone(timezone.get_current_timezone())
        if now.hour >= 12:
            next_reset = (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        else:
            next_reset = now.replace(hour=12, minute=0, second=0, microsecond=0)
        return max(0, int((next_reset - now).total_seconds()))

    def get_kitsune_gold_multiplier(self):
        """El Zorro Kitsune bendice con un bono masivo de oro al mediodía (+25% / +45% / +70%)."""
        try:
            from pets.models import Pet
            pet = Pet.objects.filter(telegram_user_id=self.telegram_user_id).first()
            if pet and pet.species == 'fox':
                stage = pet.evolution_stage_number
                return {1: 1.25, 2: 1.45, 3: 1.70}.get(stage, 1.25)
        except Exception:
            pass
        return 1.0

    # Mantenido por compatibilidad
    def get_cooldown_hours(self):
        return 24


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


class CourtJob(models.Model):
    telegram_user_id = models.BigIntegerField("ID del Trabajador", db_index=True)
    job_key = models.CharField("Código de Labor", max_length=50)
    title = models.CharField("Título de la Labor", max_length=100)
    role_type = models.CharField("Rol (cliente/idol)", max_length=20, default='cliente')
    duration_minutes = models.PositiveIntegerField("Duración en Minutos", default=20)
    finishes_at = models.DateTimeField("Termina a las")
    gold_reward = models.PositiveIntegerField("Paga en Oro", default=15)
    xp_reward = models.PositiveIntegerField("EXP Recompensa", default=5)
    is_claimed = models.BooleanField("¿Cobrado?", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def is_finished(self):
        return timezone.now() >= self.finishes_at

    def seconds_remaining(self):
        if self.is_finished():
            return 0
        return max(0, int((self.finishes_at - timezone.now()).total_seconds()))


# ==========================================
# BOUTIQUE REAL: ARTÍCULOS & COLECCIONABLES CON FOTO
# ==========================================

class CollectibleSeries(models.Model):
    name = models.CharField("Nombre de la Colección", max_length=150)
    tagline = models.CharField("Subtítulo / Edición", max_length=150, blank=True, null=True, default="Pop Mart Edition")
    description = models.TextField("Descripción del Set", max_length=400, blank=True, null=True)
    cover_image = models.ImageField("Caja / Portada de la Serie", upload_to='bazar_series/', blank=True, null=True)
    blind_box_price = models.PositiveIntegerField("Precio Caja Sorpresa (🪙)", default=160)
    single_price = models.PositiveIntegerField("Precio Compra Directa (🪙)", default=260)
    is_active = models.BooleanField("¿Serie Disponible?", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Colección / Serie Pop Mart"
        verbose_name_plural = "Colecciones / Series Pop Mart"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def total_items(self):
        return self.items.filter(is_active=True).count()


class BazarCollectible(models.Model):
    CATEGORY_CHOICES = [
        ('figura', '🎎 Figura Pop Mart'),
        ('joya', '💎 Joyería & Reliquia'),
        ('souvenir', '🎀 Merchandising VIP'),
        ('especial', '✨ Objeto Exclusivo'),
    ]

    series = models.ForeignKey(CollectibleSeries, on_delete=models.CASCADE, null=True, blank=True, related_name='items')
    name = models.CharField("Nombre de la Figura", max_length=120)
    category = models.CharField("Categoría", max_length=20, choices=CATEGORY_CHOICES, default='figura')
    description = models.TextField("Detalle", max_length=300, blank=True, null=True)
    price = models.PositiveIntegerField("Precio en Oro (🪙)", default=260)
    image = models.ImageField("Fotografía de la Figura", upload_to='bazar_collectibles/')
    stock = models.IntegerField("Stock (-1 = Ilimitado)", default=-1)
    idol_name = models.CharField("Idol o Personaje", max_length=100, blank=True, null=True)
    is_secret = models.BooleanField("¿Figura Secreta / Chase ⭐?", default=False)
    is_active = models.BooleanField("¿Disponible?", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Figura Coleccionable"
        verbose_name_plural = "Figuras Coleccionables"
        ordering = ['created_at']

    def __str__(self):
        return f"{self.name} ({self.price} 🪙)"

    @property
    def is_in_stock(self):
        return self.stock == -1 or self.stock > 0


class UserCollectible(models.Model):
    telegram_user_id = models.BigIntegerField("ID del Propietario", db_index=True)
    item = models.ForeignKey(BazarCollectible, on_delete=models.CASCADE, related_name='owners')
    quantity = models.PositiveIntegerField("Cantidad", default=1)
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Coleccionable de Usuario"
        verbose_name_plural = "Coleccionables de Usuarios"
        unique_together = ('telegram_user_id', 'item')
        ordering = ['-purchased_at']

    def __str__(self):
        return f"{self.telegram_user_id} posee {self.item.name} (x{self.quantity})"