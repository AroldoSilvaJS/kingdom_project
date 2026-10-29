from django.contrib import admin
from .models import Wallet, BazarItem, UserCollectible

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'balance', 'updated_at')
    search_fields = ('telegram_user_id',)
    list_editable = ('balance',) # Te permitirá editar el saldo directo desde la lista


@admin.register(BazarItem)
class BazarItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'idol_name', 'price', 'stock', 'is_active', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'idol_name')
    list_editable = ('price', 'stock', 'is_active')

@admin.register(UserCollectible)
class UserCollectibleAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'item', 'quantity', 'purchased_at')
    search_fields = ('telegram_user_id', 'item__name')