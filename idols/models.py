from django.db import models
from django.db.models import Avg
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
        # Validación de negocio: máximo 3 Idols por usuario
        if not self.pk:
            count = IdolProfile.objects.filter(telegram_user_id=self.telegram_user_id).count()
            if count >= 3:
                raise ValidationError("No puedes registrar más de 3 Idols.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


# --- MODELO REVIEW (pegado al borde izquierdo) ---
class Review(models.Model):
    idol = models.ForeignKey(IdolProfile, on_delete=models.CASCADE, related_name='reviews')
    client_telegram_id = models.BigIntegerField("ID del Cliente", db_index=True)
    client_username = models.CharField("Cliente", max_length=100)
    
    # Calificación de 1 a 5 estrellas
    rating = models.PositiveSmallIntegerField("Calificación (1 a 5)", default=5)
    comment = models.TextField("Comentario / Reseña", max_length=300)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Reseña"
        verbose_name_plural = "Reseñas"
        ordering = ['-created_at']

    def __str__(self):
        return f"Reseña de {self.client_username} para {self.idol.stage_name} ({self.rating}★)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Recalcular automáticamente los servicios y el rating promedio de la Idol
        all_reviews = self.idol.reviews.all()
        self.idol.services_done = all_reviews.count()
        avg_score = all_reviews.aggregate(Avg('rating'))['rating__avg']
        self.idol.rating = round(avg_score, 2) if avg_score else 5.00
        self.idol.save()

class Post(models.Model):
    NETWORK_CHOICES = [
        ('gram', 'KingdomGram (Público)'),
        ('fans', 'KingdomFans (VIP / Pago)'),
    ]
    
    idol = models.ForeignKey(IdolProfile, on_delete=models.CASCADE, related_name='posts')
    network = models.CharField("Red Social", max_length=10, choices=NETWORK_CHOICES, default='gram')
    
    image = models.ImageField("Foto del Post", upload_to='social_posts/')
    caption = models.TextField("Descripción", max_length=300)
    
    # Solo se usa si la red es 'fans'
    price = models.PositiveIntegerField("Precio en Oro (0 si es Público)", default=0)
    likes = models.PositiveIntegerField("Me Gusta", default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Publicación"
        verbose_name_plural = "Publicaciones"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_network_display()} de {self.idol.stage_name}"

class PostUnlock(models.Model):
    """Guarda el registro de qué cliente desbloqueó qué foto VIP"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='unlocks')
    client_telegram_id = models.BigIntegerField("ID del Cliente", db_index=True)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Evita que el mismo cliente compre la misma foto dos veces
        unique_together = ('post', 'client_telegram_id')

    def __str__(self):
        return f"Post #{self.post.id} desbloqueado por {self.client_telegram_id}"

# --- AGREGAR AL FINAL DE idols/models.py ---
class PostLike(models.Model):
    """Registra qué usuario le dio like a qué publicación"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='user_likes')
    client_telegram_id = models.BigIntegerField("ID del Usuario", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'client_telegram_id')

    def __str__(self):
        return f"Like en Post #{self.post.id} por {self.client_telegram_id}"
    
class UserRole(models.Model):
    telegram_id = models.CharField(max_length=100, unique=True)
    role = models.CharField(max_length=10, choices=[('idol', 'Idol'), ('cliente', 'Cliente')])

    def __str__(self):
        return f"{self.telegram_id} - {self.role}"