# pets/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta
from pets.species_registry import get_evolution_stage

class Pet(models.Model):
    SPECIES_CHOICES = [
        ('panther', 'Pantera de Ébano 🐆'),
        ('fox', 'Zorro Kitsune Dorado 🦊'),
        ('viper', 'Víbora de Esmeralda 🐍'),
        ('raven', 'Cuervo de Medianoche 🦅'),
        ('wolf', 'Lobo Espectral de Plata 🐺'),
        ('dragon', 'Dragón Carmesí 🐉'),
        ('owl', 'Búho Cronos 🦉'),
        ('deer', 'Ciervo de Jade 🦌'),
        ('scorpion', 'Escorpión Dorado 🦂'),
        ('rabbit', 'Conejo Lunar 🐇'),
    ]

    telegram_user_id = models.BigIntegerField("ID del Dueño", db_index=True, unique=True)
    name = models.CharField("Nombre de la Mascota", max_length=50)
    species = models.CharField("Especie Base", max_length=50, choices=SPECIES_CHOICES, default='fox')
    level = models.PositiveIntegerField("Nivel", default=1)
    xp = models.PositiveIntegerField("Experiencia", default=0)
    energy = models.PositiveIntegerField("Energía / Saciedad", default=80)
    happiness = models.PositiveIntegerField("Felicidad / Vínculo", default=70)
    last_fed = models.DateTimeField(null=True, blank=True)
    last_petted = models.DateTimeField(null=True, blank=True)
    last_expedition = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def stage_info(self):
        return get_evolution_stage(self.species, self.level)

    @property
    def evolution_stage_number(self):
        return self.stage_info['stage']

    @property
    def evolved_name(self):
        return self.stage_info['name']

    @property
    def xp_to_next_level(self):
        return 100 + ((self.level - 1) * 80)

    @property
    def xp_percentage(self):
        needed = self.xp_to_next_level
        return 0 if needed <= 0 else min(100, int((self.xp / needed) * 100))

    def can_be_petted(self):
        return not self.last_petted or timezone.now() >= self.last_petted + timedelta(minutes=30)

    def minutes_until_next_pet(self):
        if self.can_be_petted(): return 0
        return max(1, int(((self.last_petted + timedelta(minutes=30)) - timezone.now()).total_seconds() // 60))

    def add_xp(self, amount):
        """Maneja la experiencia y subidas de nivel en cascada de forma segura."""
        if amount <= 0:
            return (False, self.level, self.evolution_stage_number)

        old_stage = self.evolution_stage_number
        self.xp += int(amount)
        leveled_up = False

        while True:
            needed = self.xp_to_next_level
            if self.xp >= needed:
                self.xp -= needed
                self.level += 1
                leveled_up = True
            else:
                break

        new_stage = self.evolution_stage_number
        self.save()
        return (leveled_up, self.level, new_stage > old_stage)

    def feed(self):
        self.energy = min(100, self.energy + 25)
        self.happiness = min(100, self.happiness + 10)
        self.last_fed = timezone.now()
        leveled_up, _, did_evolve = self.add_xp(20)
        return did_evolve

    def pet_action(self):
        self.happiness = min(100, self.happiness + 20)
        self.last_petted = timezone.now()
        leveled_up, _, did_evolve = self.add_xp(15)
        return did_evolve

    def get_image_url(self):
        return f"/media/pets/{self.stage_info['sprite']}"

    def get_buff_description(self):
        return self.stage_info['buff_desc']

    def __str__(self):
        return f"{self.name} ({self.evolved_name}) - Nivel {self.level}"