from django.db import models
from idols.models import IdolProfile

class UserProfile(models.Model):
    telegram_user_id = models.BigIntegerField(unique=True, verbose_name="ID de Telegram")
    username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Usuario de Telegram")
    
    # --- SISTEMA DE NIVELES Y EXPERIENCIA AVANZADO (HASTA LVL 100) ---
    level = models.PositiveIntegerField(default=1, verbose_name="Nivel Nobiliario")
    current_xp = models.PositiveIntegerField(default=0, verbose_name="EXP en Nivel Actual")
    total_xp = models.PositiveIntegerField(default=0, verbose_name="EXP Histórica Total")

    title = models.CharField(
        max_length=50,
        choices=[
            ('plebeyo', 'Curioso Clandestino 🍷'),
            ('iniciado', 'Iniciado del Placer ✨'),
            ('caballero', 'Caballero VIP 🥂'),
            ('baron', 'Barón de la Fortuna 🪙'),
            ('conde', 'Conde Estelar 💎'),
            ('marques', 'Marqués del Deseo 🌹'),
            ('duque', 'Duque Imperial 👑'),
            ('soberano', 'Soberano Absoluto ⚜️'),
        ],
        default='plebeyo',
        verbose_name="Título Nobiliario"
    )

    motto = models.CharField(max_length=120, blank=True, null=True, verbose_name="Lema o Frase Insignia")
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
    
    bio = models.CharField(max_length=250, blank=True, null=True, verbose_name="Biografía / Presentación")
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

    # --- MATEMÁTICA Y CURVA DE PROGRESIÓN PROFUNDA ---
    @property
    def xp_needed_for_next_level(self):
        """
        Curva balanceada progresiva:
        Nivel 1 -> 120 XP
        Nivel 5 -> 380 XP
        Nivel 15 -> 1,150 XP
        Nivel 30 -> 2,800 XP
        Nivel 50+ -> Requiere dedicación real
        """
        lvl = max(1, self.level)
        return int(120 + ((lvl - 1) * 65) + (lvl ** 1.55 * 18))

    @property
    def xp_progress_percentage(self):
        needed = self.xp_needed_for_next_level
        if needed <= 0:
            return 0
        porcentaje = (self.current_xp / float(needed)) * 100
        return max(0, min(100, int(porcentaje)))

    @property
    def max_bet_allowed(self):
        """
        Límite dinámico de apuesta en Casino según estatus:
        Niveles 1-5: 25 🪙 (protege al novato)
        Niveles 6-15: 50 🪙
        Niveles 16-30: 100 🪙
        Niveles 31+: 200 🪙 (Sala de Grandes Apostadores)
        """
        if self.level >= 31:
            return 200
        elif self.level >= 16:
            return 100
        elif self.level >= 6:
            return 50
        return 25

    @property
    def idol_rank_name(self):
        if self.level >= 70:
            return "Reina Absoluta del Reino ⚜️"
        elif self.level >= 50:
            return "Diva Primordial del Placer 👑"
        elif self.level >= 35:
            return "Musa Consagrada Imperial 💎"
        elif self.level >= 22:
            return "Musa Clandestina Estelar 🌹"
        elif self.level >= 12:
            return "Musa de la Corte 🥂"
        elif self.level >= 5:
            return "Aspirante Exclusiva ✨"
        return "Debutante Clandestina 🎭"

    @property
    def noble_rank_name(self):
        if self.level >= 70:
            return "Soberano del Reino ⚜️"
        elif self.level >= 50:
            return "Duque Imperial 👑"
        elif self.level >= 35:
            return "Marqués del Deseo 🌹"
        elif self.level >= 22:
            return "Conde de la Fortuna 🪙"
        elif self.level >= 12:
            return "Caballero VIP 🥂"
        elif self.level >= 5:
            return "Iniciado del Placer ✨"
        return "Curioso Clandestino 🍷"

    def get_rank_name(self, is_idol=False):
        return self.idol_rank_name if is_idol else self.noble_rank_name

    def get_daily_bonus_amount(self):
        """Recompensa diaria que premia el rango alcanzado"""
        base = 30
        incremento = min(70, self.level * 2)
        return base + incremento

    def add_xp(self, amount):
        if amount <= 0:
            return (False, self.level, 0)

        self.current_xp += int(amount)
        self.total_xp += int(amount)
        leveled_up = False
        gold_reward = 0

        while True:
            costo = self.xp_needed_for_next_level
            if self.current_xp >= costo:
                self.current_xp -= costo
                self.level += 1
                leveled_up = True
                gold_reward += 20 + (self.level * 3)
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