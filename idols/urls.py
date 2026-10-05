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
    path('feed/like/<int:post_id>/', views.toggle_like, name='toggle_like'),
    path('collection/', views.my_collection, name='my_collection'),
    path('feed/tip/<int:post_id>/', views.send_tip, name='send_tip'),
    path('<int:idol_id>/custom-request/', views.create_custom_request, name='create_custom_request'),
    path('feed/comment/<int:post_id>/', views.add_comment, name='add_comment'),
    path('feed/edit/<int:post_id>/', views.edit_post, name='edit_post'),      # 👈 AÑADIR
    path('feed/delete/<int:post_id>/', views.delete_post, name='delete_post'),  # 👈 AÑADIR
    # Rutas del Sistema de Photocards y Cajas CS
    path('photocards/', views.photocard_boxes_view, name='photocard_boxes'),
    path('photocards/open/<int:box_id>/', views.open_photocard_box_ajax, name='open_box_ajax'),
    path('photocards/album/', views.my_photocards_album, name='my_photocards_album'),
    path('photocards/admin/', views.admin_photocards_manage, name='admin_photocards'),
    # Mercado e Intercambios de Photocards
    path('photocards/market/', views.photocards_market, name='photocards_market'),
    path('photocards/sell/<int:user_card_id>/', views.photocard_sell_action, name='photocard_sell_action'),
    path('photocards/buy/<int:user_card_id>/', views.photocard_buy_action, name='photocard_buy_action'),
    path('photocards/trade/create/<int:user_card_id>/', views.create_trade_offer, name='create_trade_offer'),
    path('photocards/trade/<int:trade_id>/<str:action>/', views.handle_trade_offer, name='handle_trade_offer'),
]
