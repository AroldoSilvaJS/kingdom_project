from django.db import models
from idols.models import IdolProfile

class UserProfile(models.Model):
    telegram_user_id = models.BigIntegerField(unique=True, verbose_name="ID de Telegram")
    username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Usuario de Telegram")
    title = models.CharField(
        max_length=50,
        choices=[
            ('plebeyo', 'Curioso Clandestino 🍷'),
            ('caballero', 'Caballero VIP 🥂'),
            ('conde', 'Conde de la Fortuna 🪙'),
            ('duque', 'Duque Imperial 👑'),
            ('archiduque', 'Archiduque del Placer 💎'),
        ],
        default='caballero',
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
        return f"{self.username or self.telegram_user_id} - {self.get_title_display()}"

    
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
    """Guarda valores globales como bono diario, anuncio activo, etc."""
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
    """Registra qué admin hizo cada cambio"""
    admin_tg_id = models.BigIntegerField()
    action = models.CharField(max_length=50)
    target_tg_id = models.BigIntegerField(blank=True, null=True)
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)