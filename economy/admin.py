from django.contrib import admin
from .models import Wallet

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'balance', 'updated_at')
    search_fields = ('telegram_user_id',)
    list_editable = ('balance',) # Te permitirá editar el saldo directo desde la lista