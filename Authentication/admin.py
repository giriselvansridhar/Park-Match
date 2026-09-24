from django.contrib import admin

from .models import Landlord, Parker


@admin.register(Parker)
class ParkerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "vehicle_type", "vehicle_number", "registered_at")
    search_fields = ("name", "phone", "email", "vehicle_number")
    exclude = ("pin",)


@admin.register(Landlord)
class LandlordAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "city")
    search_fields = ("name", "phone", "email", "city")
    exclude = ("pin",)
