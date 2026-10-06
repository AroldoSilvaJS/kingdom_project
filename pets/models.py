# pets/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta
from pets.species_registry import get_evolution_stage, get_species_data

class Pet(models.Model):
    telegram_user_id = models.BigIntegerField("ID del Dueño", db_index=True, unique=True)
    name = models.CharField("Nombre de la Mascota", max_length=50)
    species = models.CharField("Especie Base", max_length=50, default='fox')

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
        """Retorna la fase evolutiva actual (1, 2 o 3) según el nivel"""
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
        if needed <= 0:
            return 0
        return min(100, int((self.xp / needed) * 100))

    def can_be_petted(self):
        if not self.last_petted:
            return True
        return timezone.now() >= self.last_petted + timedelta(minutes=30)

    def minutes_until_next_pet(self):
        if self.can_be_petted():
            return 0
        tiempo_restante = (self.last_petted + timedelta(minutes=30)) - timezone.now()
        return max(1, int(tiempo_restante.total_seconds() // 60))

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
        """Acaricia a la mascota aumentando vínculo y experiencia"""
        self.happiness = min(100, self.happiness + 20)
        self.xp += 15
        if self.xp >= self.xp_to_next_level:
            self.xp -= self.xp_to_next_level
            self.level += 1
        self.last_petted = timezone.now()
        self.save()

    def get_image_url(self):
        sprite_filename = self.stage_info['sprite']
        return f"/media/pets/{sprite_filename}"

    def get_buff_description(self):
        return self.stage_info['buff_desc']

    def __str__(self):
        return f"{self.name} ({self.evolved_name}) - Nivel {self.level}"