from django.contrib import admin

from .models import Booking, ParkingSpot, Review


@admin.register(ParkingSpot)
class ParkingSpotAdmin(admin.ModelAdmin):
    list_display = ("title", "landlord", "city", "hourly_rate", "capacity", "instant_book", "is_active")
    list_filter = ("is_active", "instant_book", "city")
    search_fields = ("title", "address", "landlord__name")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("code", "parker", "spot", "start", "end", "total_price", "status")
    list_filter = ("status",)
    search_fields = ("parker__name", "spot__title", "vehicle_number")


admin.site.register(Review)
