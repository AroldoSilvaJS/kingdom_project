from django.db import models
from idols.models import IdolProfile

class UserProfile(models.Model):
    telegram_user_id = models.BigIntegerField(unique=True, verbose_name="ID de Telegram")
    username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Usuario de Telegram")
    
    # --- SISTEMA DE NIVELES Y EXPERIENCIA BALANCEADO ---
    level = models.PositiveIntegerField(default=1, verbose_name="Nivel Nobiliario")
    current_xp = models.PositiveIntegerField(default=0, verbose_name="EXP Acumulada en Nivel Actual")
    total_xp = models.PositiveIntegerField(default=0, verbose_name="EXP Histórica Total")

    title = models.CharField(
        max_length=50,
        choices=[
            ('plebeyo', 'Curioso Clandestino 🍷'),
            ('caballero', 'Caballero VIP 🥂'),
            ('conde', 'Conde de la Fortuna 🪙'),
            ('duque', 'Duque Imperial 👑'),
            ('archiduque', 'Archiduque del Placer 💎'),
        ],
        default='plebeyo',
        verbose_name="Título Nobiliario"
    )

    motto = models.CharField(max_length=100, blank=True, null=True, verbose_name="Lema o Frase Insignia")
    profile_theme = models.CharField(
        max_length=30,
        choices=[
            ('velvet', 'Terciopelo Imperial'),
            ('obsidian', 'Obsidiana & Neón'),
            ('crimson', 'Carmesí Clandestino'),
            ('champagne', 'Champagne Real'),
        ],
        default='velvet',
        verbose_name="Tema de Fondo"
    )
    vip_badge = models.CharField(
        max_length=30,
        choices=[
            ('none', 'Sin Insignia'),
            ('high_roller', '🎰 High Roller Casino'),
            ('mecenas', '💎 Mecenas Imperial'),
            ('romantico', '🌹 Caballero Devoto'),
            ('coleccionista', '🐾 Domador de Bestias'),
        ],
        default='none',
        verbose_name="Insignia Nobiliaria"
    )
    
    bio = models.CharField(max_length=200, blank=True, null=True, verbose_name="Biografía / Presentación")
    avatar_frame = models.CharField(
        max_length=20,
        choices=[
            ('gold', 'Borde Oro Pulido 👑'),
            ('neon', 'Borde Neón Púrpura 🟣'),
            ('diamond', 'Borde Diamante Glacial 💎'),
            ('flame', 'Borde Llama Carmesí 🔥'),
        ],
        default='gold',
        verbose_name="Marco de Avatar"
    )
    favorite_idol = models.ForeignKey(
        IdolProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="devoted_nobles",
        verbose_name="Musa / Idol Favorita"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username or self.telegram_user_id} - Nivel {self.level}"

    # --- MATEMÁTICA Y CURVA DE PROGRESIÓN ---
    # --- MATEMÁTICA Y CURVA DE PROGRESIÓN ESTABLE ---
    @property
    def xp_needed_for_next_level(self):
        """Curva de EXP balanceada: Nivel 1 = 100 XP, Nivel 2 = 140 XP, etc."""
        return int(100 + ((self.level - 1) * 40) + ((self.level - 1) ** 1.35 * 15))

    @property
    def xp_progress_percentage(self):
        """Porcentaje de progreso exacto del 0 al 100 para la barra visual"""
        needed = self.xp_needed_for_next_level
        if needed <= 0:
            return 0
        porcentaje = (self.current_xp / float(needed)) * 100
        return max(0, min(100, int(porcentaje)))

    @property
    def idol_rank_name(self):
        """Rango escénico para Idols"""
        if self.level >= 45:
            return "Reina Absoluta del Placer 👑"
        elif self.level >= 30:
            return "Diva Consagrada del Reino 💎"
        elif self.level >= 18:
            return "Musa Clandestina Estelar 🌹"
        elif self.level >= 8:
            return "Musa de la Corte ✨"
        return "Debutante Exclusiva 🎭"

    @property
    def noble_rank_name(self):
        """Rango feudal para Clientes Nobles"""
        if self.level >= 45:
            return "Archiduque del Placer 💎"
        elif self.level >= 30:
            return "Duque Imperial 👑"
        elif self.level >= 18:
            return "Conde de la Fortuna 🪙"
        elif self.level >= 8:
            return "Caballero VIP 🥂"
        return "Curioso Clandestino 🍷"

    def get_rank_name(self, is_idol=False):
        return self.idol_rank_name if is_idol else self.noble_rank_name

    def get_daily_bonus_amount(self):
        """Bono diario escalonado balanceado según el nivel"""
        if self.level >= 45:
            return 50
        elif self.level >= 25:
            return 45
        elif self.level >= 10:
            return 40
        return 35

    def add_xp(self, amount):
        """
        Suma EXP de forma segura, maneja saltos de múltiples niveles 
        y recompensa con oro sin desbordar la experiencia.
        """
        if amount <= 0:
            return (False, self.level, 0)

        self.current_xp += int(amount)
        self.total_xp += int(amount)
        leveled_up = False
        gold_reward = 0

        # Procesar ascensos uno por uno con el costo exacto de cada nivel
        while True:
            costo_nivel_actual = self.xp_needed_for_next_level
            if self.current_xp >= costo_nivel_actual:
                self.current_xp -= costo_nivel_actual
                self.level += 1
                leveled_up = True
                gold_reward += 15 + (self.level * 2)
            else:
                break

        self.save()
        return (leveled_up, self.level, gold_reward)


class UserRole(models.Model):
    ROLES = [
        ('admin', 'Administrador Supremo 👑'),
        ('moderador', 'Moderador Imperial 🛡️'),
        ('idol', 'Musa / Creadora VIP 🌹'),
        ('vip', 'Noble VIP 🥂'),
        ('cliente', 'Súbdito Ordinario 🍷'),
    ]
    telegram_id = models.BigIntegerField(unique=True, verbose_name="ID de Telegram")
    role = models.CharField(max_length=20, choices=ROLES, default='cliente')
    is_banned = models.BooleanField(default=False, verbose_name="¿Baneado?")
    ban_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name="Motivo de Suspensión")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.telegram_id} - {self.role}"

class KingdomSetting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.TextField()

    @classmethod
    def get_val(cls, key, default=''):
        obj = cls.objects.filter(key=key).first()
        return obj.value if obj else default

    @classmethod
    def set_val(cls, key, value):
        cls.objects.update_or_create(key=key, defaults={'value': str(value)})

class AdminAuditLog(models.Model):
    admin_tg_id = models.BigIntegerField()
    action = models.CharField(max_length=50)
    target_tg_id = models.BigIntegerField(blank=True, null=True)
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)