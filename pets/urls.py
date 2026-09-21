from django.urls import path
from . import views

app_name = 'pets'

urlpatterns = [
    path('', views.pet_sanctuary, name='sanctuary'),
    path('adopt/', views.adopt_pet, name='adopt'),
    path('interact/', views.interact_pet, name='interact'),
    path('change/', views.change_pet, name='change_pet'),
]