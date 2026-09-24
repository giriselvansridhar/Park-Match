from django.urls import path

from Authentication import views

urlpatterns = [
    path('', views.home, name="home"),
    path('login/', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    path('demo/<str:role>/', views.demo_login, name="demo_login"),
    path('signup/parker/', views.parker_sign_up, name="Parker_Register"),
    path('signup/landlord/', views.landlord_signup, name="LandLord_Register"),
    path('overview/', views.dashboard_view, name='dashboard'),
]
