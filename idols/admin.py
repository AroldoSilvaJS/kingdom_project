from django.contrib import admin
from .models import IdolProfile, Review, Post, PostUnlock

@admin.register(IdolProfile)
class IdolProfileAdmin(admin.ModelAdmin):
    list_display = ('stage_name', 'owner_username', 'group', 'services_done', 'rating', 'created_at')
    search_fields = ('stage_name', 'owner_username', 'group')
    list_filter = ('created_at',)

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('idol', 'client_username', 'rating', 'created_at')
    search_fields = ('client_username', 'idol__stage_name')
    list_filter = ('rating', 'created_at')
    
    
admin.site.register(Post)
admin.site.register(PostUnlock)