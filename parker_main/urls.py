from django.urls import path

from parker_main import views

urlpatterns = [
    path('', views.Parker_main, name='Parker_main'),
    path('spots/<int:spot_id>/', views.spot_detail, name='spot_detail'),
    path('spots/<int:spot_id>/directions/', views.spot_directions, name='spot_directions'),
    path('bookings/', views.parker_bookings, name='parker_bookings'),
    path('bookings/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    path('bookings/<int:booking_id>/review/', views.review_booking, name='review_booking'),
]
