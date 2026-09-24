from django.urls import path

from parker_main import views

urlpatterns = [
    path('', views.landlord_dashboard, name='landlord_dashboard'),
    path('bookings/', views.landlord_bookings, name='landlord_bookings'),
    path('bookings/<int:booking_id>/<str:action>/', views.booking_respond, name='booking_respond'),
    path('spots/new/', views.spot_create, name='spot_create'),
    path('spots/<int:spot_id>/edit/', views.spot_edit, name='spot_edit'),
    path('spots/<int:spot_id>/toggle/', views.spot_toggle, name='spot_toggle'),
]
