from django.urls import path
from . import views

app_name = 'idols'

urlpatterns = [
    path('', views.idol_list, name='list'),
    path('create/', views.idol_create, name='create'),
    path('edit/<int:idol_id>/', views.idol_edit, name='edit'),     # <- NUEVA
    path('delete/<int:idol_id>/', views.idol_delete, name='delete'), # <- NUEVA
    path('gallery/', views.idol_gallery, name='gallery'), # <- AÑADIR ESTA LÍNEA
]