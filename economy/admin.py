from django.contrib import admin
from .models import Wallet, UserInventoryItem, CourtJob, BazarCollectible, UserCollectible

# 🪙 BÓVEDAS DE USUARIOS (Lo que se había borrado)
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'balance', 'patron_vault', 'last_bonus_claim', 'updated_at')
    search_fields = ('telegram_user_id',)
    list_editable = ('balance',)  # Permite editar el oro directamente desde la lista

# 🏺 BOUTIQUE REAL: COLECCIONABLES CON FOTO
@admin.register(BazarCollectible)
class BazarCollectibleAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'idol_name', 'price', 'stock', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'idol_name')
    list_editable = ('price', 'stock', 'is_active')

# 📦 COLECCIONABLES EN POSESIÓN DE USUARIOS
@admin.register(UserCollectible)
class UserCollectibleAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'item', 'quantity', 'purchased_at')
    search_fields = ('telegram_user_id', 'item__name')
    list_filter = ('purchased_at',)

# 🎒 INVENTARIO DE OBJETOS CONSUMIBLES
@admin.register(UserInventoryItem)
class UserInventoryItemAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'item_code', 'quantity', 'updated_at')
    search_fields = ('telegram_user_id', 'item_code')

# 💼 LABORES DE LA CORTE (TRABAJOS ACTIVOS)
@admin.register(CourtJob)
class CourtJobAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'title', 'role_type', 'gold_reward', 'xp_reward', 'is_claimed', 'finishes_at')
    list_filter = ('role_type', 'is_claimed')
    search_fields = ('telegram_user_id', 'title')