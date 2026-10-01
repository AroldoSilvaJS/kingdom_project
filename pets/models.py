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
    happiness = models.PositiveIntegerField("Felicidad / Vínculo", default=75)
    
    last_fed = models.DateTimeField(auto_now_add=True)
    last_petted = models.DateTimeField(auto_now_add=True)
    last_expedition = models.DateTimeField(null=True, blank=True, verbose_name="Última Expedición")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def xp_to_next_level(self):
        return self.level * 100

    @property
    def xp_percentage(self):
        needed = self.xp_to_next_level
        if needed <= 0:
            return 0
        return min(100, int((self.xp / needed) * 100))

    def xp_needed_for_next_level(self):
        return self.level * 100

    def feed(self):
        self.energy = min(100, self.energy + 25)
        self.happiness = min(100, self.happiness + 15)
        self.xp += 30
        if self.xp >= self.xp_needed_for_next_level():
            self.xp -= self.xp_needed_for_next_level()
            self.level += 1
        self.last_fed = timezone.now()
        self.save()

    def pet_action(self):
        self.happiness = min(100, self.happiness + 20)
        self.xp += 10
        if self.xp >= self.xp_needed_for_next_level():
            self.xp -= self.xp_needed_for_next_level()
            self.level += 1
        self.last_petted = timezone.now()
        self.save()

    def can_go_expedition(self):
        """Puede salir a cazar/explorar cada 2 horas"""
        if not self.last_expedition:
            return True
        return timezone.now() >= self.last_expedition + timedelta(hours=2)

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