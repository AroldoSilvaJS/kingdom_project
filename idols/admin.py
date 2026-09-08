from django.contrib import admin
from .models import IdolProfile

@admin.register(IdolProfile)
class IdolProfileAdmin(admin.ModelAdmin):
    list_display = ('stage_name', 'telegram_user_id', 'group', 'services_done', 'rating', 'created_at')
    search_fields = ('stage_name', 'telegram_user_id', 'group')
    list_filter = ('created_at',)