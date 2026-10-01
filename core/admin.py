from django.contrib import admin
from .models import UserProfile, UserRole, KingdomSetting, AdminAuditLog

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'role', 'is_banned', 'created_at')
    search_fields = ('telegram_id',)
    list_filter = ('role', 'is_banned')
    list_editable = ('role', 'is_banned')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('telegram_user_id', 'username', 'level', 'current_xp', 'title', 'created_at')
    search_fields = ('telegram_user_id', 'username')
    list_filter = ('level', 'title')

@admin.register(KingdomSetting)
class KingdomSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')

@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ('admin_tg_id', 'action', 'target_tg_id', 'created_at')