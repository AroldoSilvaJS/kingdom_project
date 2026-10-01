from django.db import models
from django.utils import timezone
from datetime import timedelta

class Pet(models.Model):
    SPECIES_CHOICES = [
        ('panther', 'Pantera de Ébano 🐆'),
        ('fox', 'Zorro Kitsune Dorado 🦊'),
        ('viper', 'Víbora de Esmeralda 🐍'),
        ('raven', 'Cuervo de Medianoche 🦅'),
        ('wolf', 'Lobo Espectral de Plata 🐺'),
    ]

    telegram_user_id = models.BigIntegerField("ID del Dueño", db_index=True, unique=True)
    name = models.CharField("Nombre de la Mascota", max_length=50)
    species = models.CharField("Especie", max_length=20, choices=SPECIES_CHOICES)
    
    level = models.PositiveIntegerField("Nivel", default=1)
    xp = models.PositiveIntegerField("Experiencia", default=0)
    energy = models.PositiveIntegerField("Energía / Saciedad", default=80)
    happiness = models.PositiveIntegerField("Felicidad / Vínculo", default=70)
    
    last_fed = models.DateTimeField(null=True, blank=True)
    last_petted = models.DateTimeField(null=True, blank=True)
    last_expedition = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def xp_to_next_level(self):
        # Curva de nivel de mascota: Nivel 1 = 100, Nivel 2 = 180, Nivel 3 = 260...
        return 100 + ((self.level - 1) * 80)

    @property
    def xp_percentage(self):
        needed = self.xp_to_next_level
        if needed <= 0:
            return 0
        return min(100, int((self.xp / needed) * 100))

    # --- REGLA 1: COOLDOWN DE CARICIAS (30 MINUTOS) ---
    def can_be_petted(self):
        if not self.last_petted:
            return True
        return timezone.now() >= self.last_petted + timedelta(minutes=30)

    def minutes_until_next_pet(self):
        if self.can_be_petted():
            return 0
        tiempo_restante = (self.last_petted + timedelta(minutes=30)) - timezone.now()
        return max(1, int(tiempo_restante.total_seconds() // 60))

    # --- REGLA 2: COOLDOWN DE EXPEDICIÓN (1 HORA Y MEDIA) ---
    def can_go_expedition(self):
        if not self.last_expedition:
            return True
        return timezone.now() >= self.last_expedition + timedelta(minutes=90)

    def minutes_until_next_expedition(self):
        if self.can_go_expedition():
            return 0
        tiempo_restante = (self.last_expedition + timedelta(minutes=90)) - timezone.now()
        return max(1, int(tiempo_restante.total_seconds() // 60))

    def feed(self):
        """Alimenta a la mascota sin pasar del 100% de energía"""
        self.energy = min(100, self.energy + 25)
        self.happiness = min(100, self.happiness + 10)
        self.xp += 20
        if self.xp >= self.xp_to_next_level:
            self.xp -= self.xp_to_next_level
            self.level += 1
        self.last_fed = timezone.now()
        self.save()

    def pet_action(self):
        """Acaricia a la mascota (solo si el cooldown lo permite)"""
        self.happiness = min(100, self.happiness + 20)
        self.xp += 15
        if self.xp >= self.xp_to_next_level:
            self.xp -= self.xp_to_next_level
            self.level += 1
        self.last_petted = timezone.now()
        self.save()

    def get_image_url(self):
        mapping = {
            'fox': 'fox.png',
            'zorro': 'fox.png',
            'panther': 'panther.png',
            'pantera': 'panther.png',
            'raven': 'raven.png',
            'cuervo': 'raven.png',
            'viper': 'viper.png',
            'vibora': 'viper.png',
            'wolf': 'wolf.png',
            'lobo': 'wolf.png',
        }
        filename = mapping.get(str(self.species).lower(), 'fox.png')
        return f"/media/pets/{filename}"

    def get_buff_description(self):
        buffs = {
            'panther': '+10% de Oro extra en victorias de Casino',
            'fox': 'Bono Diario cada 22h (en vez de 24h)',
            'viper': '15% de Descuento en fotos de KingdomFans',
            'raven': '+20% de probabilidad de Jackpots en Slots',
            'wolf': '10% de Protección contra derrotas en Blackjack',
        }
        return buffs.get(self.species, 'Bendición Real Activa')

    def __str__(self):
        return f"{self.name} ({self.get_species_display()}) - Nivel {self.level}"