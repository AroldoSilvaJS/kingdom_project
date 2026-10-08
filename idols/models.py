from django.db import models
from django.db.models import Avg
from django.core.exceptions import ValidationError
import os

class IdolProfile(models.Model):

    STATUS_CHOICES = [
        ('online', '🟢 Chateando en Telegram'),
        ('antojos', '🔥 Sesión de Antojos'),
        ('offline', '🌙 Descansando'),
    ]

    telegram_user_id = models.BigIntegerField(db_index=True)
    owner_username = models.CharField("Usuario de Telegram", max_length=100, blank=True, null=True)
    
    stage_name = models.CharField("Nombre Artístico", max_length=100)
    group = models.CharField("Grupo/Solista", max_length=100, blank=True, null=True)
    bio = models.TextField("Biografía / Presentación", max_length=500)
    status = models.CharField("Estado Actual", max_length=10, choices=STATUS_CHOICES, default='online')

    photo = models.ImageField("Foto de Perfil", upload_to='idols_photos/', blank=True, null=True)
    
    services_done = models.IntegerField("Servicios Realizados", default=0)
    rating = models.DecimalField("Calificación Promedio", max_digits=3, decimal_places=2, default=5.00)

    banner = models.ImageField(upload_to='idols_banners/', blank=True, null=True, verbose_name="Foto de Portada")
    tagline = models.CharField(max_length=120, blank=True, null=True, verbose_name="Subtítulo / Esencia")
    welcome_message = models.CharField(max_length=200, blank=True, null=True, verbose_name="Saludo de Bienvenida")
    aura_color = models.CharField(
        max_length=30,
        choices=[
            ('purple', 'Aura Mística Púrpura 💜'),
            ('gold', 'Aura Celestial Dorada 💛'),
            ('ruby', 'Aura Pasión Rubí ❤️'),
            ('emerald', 'Aura Seducción Esmeralda 💚'),
        ],
        default='purple',
        verbose_name="Aura de la Idol"
    )

    specialty = models.CharField(max_length=100, blank=True, null=True, verbose_name="Especialidad")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_featured_until = models.DateTimeField(null=True, blank=True, verbose_name="Destacada en Galería hasta")

    @property
    def is_featured(self):
        from django.utils import timezone
        return bool(self.is_featured_until and timezone.now() < self.is_featured_until)

    class Meta:
        verbose_name = "Perfil de Idol"
        verbose_name_plural = "Perfiles de Idols"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.stage_name} (Dueño: {self.telegram_user_id})"

    def clean(self):
        # Validación de negocio: máximo 2 Idols por usuario
        if not self.pk:
            count = IdolProfile.objects.filter(telegram_user_id=self.telegram_user_id).count()
            if count >= 2:
                raise ValidationError("No puedes registrar más de 2 Idols.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_display_owner(self):
        """Muestra el @ o Nombre de usuario real de Telegram, NUNCA 'Noble_ID' ni números"""
        # 1. Primero consultar en UserProfile del creador
        try:
            from core.models import UserProfile
            prof = UserProfile.objects.filter(telegram_user_id=self.telegram_user_id).first()
            if prof and prof.username:
                u_str = str(prof.username).strip()
                if not u_str.isdigit() and not u_str.lower().startswith('noble_') and u_str not in ['None', '', 'undefined']:
                    return u_str if u_str.startswith('@') else f"@{u_str}"
        except Exception:
            pass

        # 2. Si no, verificar el owner_username guardado en la Idol
        if self.owner_username:
            o_str = str(self.owner_username).strip()
            if not o_str.isdigit() and not o_str.lower().startswith('noble_') and o_str not in ['None', '', 'undefined']:
                return o_str if o_str.startswith('@') else f"@{o_str}"

        # 3. Si es el Administrador Supremo
        if str(self.telegram_user_id) == '7474444797':
            return "@CoronaImperial"

        return "@MusaReal"


class Review(models.Model):
    idol = models.ForeignKey(IdolProfile, on_delete=models.CASCADE, related_name='reviews')
    client_telegram_id = models.BigIntegerField("ID del Cliente", db_index=True)
    client_username = models.CharField("Cliente", max_length=100)
    
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
    
    # Imagen (opcional si sube video)
    image = models.ImageField("Foto del Post", upload_to='social_posts/', blank=True, null=True)
    # 👈 NUEVO: Campo de Video para MP4/WebM
    video = models.FileField("Video del Post", upload_to='social_videos/', blank=True, null=True)
    
    caption = models.TextField("Descripción", max_length=300)
    price = models.PositiveIntegerField("Precio en Oro (0 si es Público)", default=0)
    likes = models.PositiveIntegerField("Me Gusta", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Publicación"
        verbose_name_plural = "Publicaciones"
        ordering = ['-created_at']

    def __str__(self):
        tipo = "Video" if self.is_video else "Foto"
        return f"{self.get_network_display()} ({tipo}) de {self.idol.stage_name}"

    @property
    def is_video(self):
        """Verifica si la publicación contiene un archivo de video"""
        return bool(self.video)

    @property
    def media_url(self):
        """Retorna la URL del archivo multimedia (video o imagen)"""
        if self.video:
            return self.video.url
        elif self.image:
            return self.image.url
        return ""

    def save(self, *args, **kwargs):
        """Optimización y compresión automática solo si es imagen"""
        super().save(*args, **kwargs)
        if self.image and not self.video:
            try:
                from PIL import Image
                img_path = self.image.path
                if os.path.exists(img_path):
                    img = Image.open(img_path)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    if img.height > 1200 or img.width > 1200:
                        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                        img.save(img_path, 'JPEG', quality=85, optimize=True)
            except Exception:
                pass


class PostUnlock(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='unlocks')
    client_telegram_id = models.BigIntegerField("ID del Cliente", db_index=True)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'client_telegram_id')

    def __str__(self):
        return f"Post #{self.post.id} desbloqueado por {self.client_telegram_id}"


class PostLike(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='user_likes')
    client_telegram_id = models.BigIntegerField("ID del Usuario", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'client_telegram_id')

    def __str__(self):
        return f"Like en Post #{self.post.id} por {self.client_telegram_id}"


class CustomRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('accepted', 'Entregada'),
        ('rejected', 'Rechazada'),
    ]
    
    idol = models.ForeignKey(IdolProfile, on_delete=models.CASCADE, related_name='custom_requests')
    client_telegram_id = models.BigIntegerField("ID del Cliente", db_index=True)
    client_username = models.CharField("Cliente", max_length=100)
    
    description = models.TextField("Detalle del Antojo", max_length=300)
    bounty = models.PositiveIntegerField("Oro Ofrecido", default=100)
    status = models.CharField("Estado", max_length=10, choices=STATUS_CHOICES, default='pending')
    
    delivered_photo = models.ImageField("Foto Entregada", upload_to='custom_antojos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Petición de Antojo"
        verbose_name_plural = "Peticiones de Antojos"
        ordering = ['-created_at']

    def __str__(self):
        return f"Antojo para {self.idol.stage_name} de {self.client_username} ({self.bounty} 🪙)"


class PostComment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author_telegram_id = models.BigIntegerField("ID del Autor", db_index=True)
    author_name = models.CharField("Nombre o @ de Usuario", max_length=100)
    text = models.TextField("Comentario", max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comentario de Post"
        verbose_name_plural = "Comentarios de Posts"
        ordering = ['created_at']

    def __str__(self):
        return f"Comentario de {self.author_name} en Post #{self.post.id}"


    # --- SISTEMA DE PHOTOCARDS Y CAJAS CS ---

class PhotocardBox(models.Model):
    name = models.CharField("Nombre de la Caja", max_length=100)
    description = models.TextField("Descripción / Temática", max_length=300)
    price = models.PositiveIntegerField("Costo de Apertura (🪙)", default=50)
    cover_image = models.ImageField("Portada de la Caja", upload_to='photocard_boxes/', blank=True, null=True)
    is_active = models.BooleanField("¿Activa para abrir?", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Caja de Photocards"
        verbose_name_plural = "Cajas de Photocards"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.price} 🪙)"


class Photocard(models.Model):
    RARITY_CHOICES = [
        ('common', 'Común ⚪'),
        ('rare', 'Rara 🔵'),
        ('epic', 'Épica 🟣'),
        ('legendary', 'Legendaria 👑'),
    ]

    box = models.ForeignKey(PhotocardBox, on_delete=models.SET_NULL, null=True, blank=True, related_name='cards', verbose_name="Caja a la que pertenece")
    idol = models.ForeignKey(IdolProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='photocards', verbose_name="Musa del Rol (Opcional)")
    idol_name = models.CharField("Idol de K-Pop / Artista", max_length=100, default='', blank=True) # 👈 LIBRE PARA CUALQUIER IDOL
    name = models.CharField("Nombre de la Carta", max_length=100)
    rarity = models.CharField("Rareza", max_length=20, choices=RARITY_CHOICES, default='common')
    image = models.ImageField("Imagen Photocard (Canva)", upload_to='photocards/')
    created_by_tg_id = models.BigIntegerField("ID del Admin Creador")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Photocard"
        verbose_name_plural = "Photocards"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_rarity_display()}] {self.name} - {self.display_idol_name}"

    @property
    def display_idol_name(self):
        if self.idol_name and self.idol_name.strip():
            return self.idol_name.strip()
        if self.idol:
            return self.idol.stage_name
        return "K-Pop Idol"

    def get_color_hex(self):
        mapping = {
            'common': '#9ca3af',      # Gris
            'rare': '#3b82f6',        # Azul CS
            'epic': '#a855f7',        # Púrpura CS
            'legendary': '#eab308',   # Dorado Legendario
        }
        return mapping.get(self.rarity, '#9ca3af')


class UserPhotocard(models.Model):
    telegram_user_id = models.BigIntegerField("ID del Dueño (Idol o Noble)", db_index=True)
    photocard = models.ForeignKey(Photocard, on_delete=models.CASCADE, related_name='owners')
    obtained_at = models.DateTimeField(auto_now_add=True)

    # 👈 Campos para Mercado de Venta
    is_for_sale = models.BooleanField("¿Puesta a la venta?", default=False)
    sale_price = models.PositiveIntegerField("Precio de Venta (🪙)", default=0, blank=True, null=True)

    class Meta:
        verbose_name = "Photocard de Usuario"
        verbose_name_plural = "Photocards de Usuarios"
        ordering = ['-obtained_at']

    def __str__(self):
        return f"{self.telegram_user_id} tiene {self.photocard.name}"


class PhotocardTrade(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente ⏳'),
        ('accepted', 'Aceptado ✅'),
        ('rejected', 'Rechazado ❌'),
        ('cancelled', 'Cancelado 🚫'),
    ]

    sender_telegram_id = models.BigIntegerField("Emisor", db_index=True)
    sender_username = models.CharField("Usuario Emisor", max_length=100, default='Noble')
    sender_card = models.ForeignKey(UserPhotocard, on_delete=models.CASCADE, related_name='trades_sent')

    receiver_telegram_id = models.BigIntegerField("Receptor", db_index=True)
    receiver_username = models.CharField("Usuario Receptor", max_length=100, default='Noble')
    receiver_card = models.ForeignKey(UserPhotocard, on_delete=models.SET_NULL, null=True, blank=True, related_name='trades_received')

    status = models.CharField("Estado", max_length=15, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Intercambio de Photocard"
        verbose_name_plural = "Intercambios de Photocards"
        ordering = ['-created_at']

    def __str__(self):
        return f"Trade #{self.id}: {self.sender_username} -> {self.receiver_username} ({self.get_status_display()})"


class IdolTribute(models.Model):
    idol = models.ForeignKey(IdolProfile, on_delete=models.CASCADE, related_name='tributes', verbose_name="Musa Agasajada")
    client_telegram_id = models.BigIntegerField("ID del Noble Emisor", db_index=True)
    client_username = models.CharField("Noble Emisor", max_length=100)
    gift_name = models.CharField("Obsequio de Corte", max_length=100)
    gold_value = models.PositiveIntegerField("Valor en Oro", default=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tributo de Musa"
        verbose_name_plural = "Tributos de Musas"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.gift_name} para {self.idol.stage_name} de {self.client_username}"