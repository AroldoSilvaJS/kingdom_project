from django.urls import path
from . import views

app_name = 'idols'

urlpatterns = [
    path('', views.idol_list, name='list'),
    path('create/', views.idol_create, name='create'),
    path('edit/<int:idol_id>/', views.idol_edit, name='edit'),
    path('delete/<int:idol_id>/', views.idol_delete, name='delete'),
    path('gallery/', views.idol_gallery, name='gallery'),
    path('<int:idol_id>/', views.idol_detail, name='detail'), # <- Esta es la clave
    path('feed/', views.social_feed, name='social_feed'),
    path('feed/unlock/<int:post_id>/', views.unlock_post, name='unlock_post'),
    path('feed/new/', views.create_post, name='create_post'), # <- AÑADIR ESTA
    path('feed/unlock/<int:post_id>/', views.unlock_post, name='unlock_post'),
    path('feed/like/<int:post_id>/', views.toggle_like, name='toggle_like'),
    path('collection/', views.my_collection, name='my_collection'),
    path('feed/tip/<int:post_id>/', views.send_tip, name='send_tip'),
    path('<int:idol_id>/custom-request/', views.create_custom_request, name='create_custom_request'),
    path('feed/comment/<int:post_id>/', views.add_comment, name='add_comment'),
]
