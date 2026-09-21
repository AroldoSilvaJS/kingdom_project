from django.db import models
from django.utils import timezone
from datetime import timedelta

class Pet(models.Model):
    SPECIES_CHOICES = [
        ('panther', 'Pantera de Ébano'),
        ('fox', 'Zorro Kitsune Dorado'),
        ('viper', 'Víbora de Esmeralda'),
        ('raven', 'Cuervo de Medianoche'),
        ('wolf', 'Lobo Espectral de Plata'),
    ]

    telegram_user_id = models.BigIntegerField("ID del Dueño", db_index=True, unique=True)
    name = models.CharField("Nombre de la Mascota", max_length=50)
    species = models.CharField("Especie", max_length=20, choices=SPECIES_CHOICES)
    
    level = models.PositiveIntegerField("Nivel", default=1)
    xp = models.PositiveIntegerField("Experiencia", default=0)
    energy = models.PositiveIntegerField("Energía / Saciedad", default=80)
    
    last_fed = models.DateTimeField(auto_now_add=True)
    last_petted = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def xp_needed_for_next_level(self):
        return self.level * 100

    def feed(self):
        self.energy = min(100, self.energy + 25)
        self.xp += 30
        if self.xp >= self.xp_needed_for_next_level():
            self.xp -= self.xp_needed_for_next_level()
            self.level += 1
        self.last_fed = timezone.now()
        self.save()

    def pet_action(self):
        self.xp += 10
        if self.xp >= self.xp_needed_for_next_level():
            self.xp -= self.xp_needed_for_next_level()
            self.level += 1
        self.last_petted = timezone.now()
        self.save()

    def get_image_url(self):
        return f"/media/pets/{self.species}.png"

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