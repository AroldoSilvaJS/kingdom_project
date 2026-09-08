from django.db import models
from django.core.exceptions import ValidationError

class IdolProfile(models.Model):
    # Relacionamos este perfil directamente con el ID numérico de Telegram del usuario
    telegram_user_id = models.BigIntegerField(db_index=True)
    owner_username = models.CharField("Usuario de Telegram", max_length=100, blank=True, null=True)
    
    # Datos del personaje
    stage_name = models.CharField("Nombre Artístico", max_length=100)
    group = models.CharField("Grupo/Solista", max_length=100, blank=True, null=True)
    bio = models.TextField("Biografía / Presentación", max_length=500)
    
    photo = models.ImageField("Foto de Perfil", upload_to='idols_photos/', blank=True, null=True)
    
    # Estadísticas básicas para la ficha
    services_done = models.IntegerField("Servicios Realizados", default=0)
    rating = models.DecimalField("Calificación Promedio", max_digits=3, decimal_places=2, default=5.00)

    # Fechas de control
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil de Idol"
        verbose_name_plural = "Perfiles de Idols"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.stage_name} (Dueño: {self.telegram_user_id})"

    def clean(self):
        # Esta es la validación a nivel de base de datos para el límite de 3 idols
        if not self.pk: # Solo validamos al crear un personaje nuevo
            count = IdolProfile.objects.filter(telegram_user_id=self.telegram_user_id).count()
            if count >= 3:
                raise ValidationError("No puedes registrar más de 3 Idols.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)