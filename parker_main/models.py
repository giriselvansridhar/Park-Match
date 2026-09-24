from decimal import Decimal
from math import atan2, cos, radians, sin, sqrt

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone

from Authentication.models import Landlord, Parker


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


class ParkingSpot(models.Model):
    landlord = models.ForeignKey(Landlord, on_delete=models.CASCADE, related_name="spots")
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    photo = models.ImageField(upload_to="spot_photos/", null=True, blank=True)

    hourly_rate = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    capacity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(500)])
    accepts_car = models.BooleanField(default=True)
    accepts_bike = models.BooleanField(default=True)

    is_covered = models.BooleanField("Covered", default=False)
    has_cctv = models.BooleanField("CCTV", default=False)
    has_ev_charging = models.BooleanField("EV charging", default=False)
    has_guard = models.BooleanField("Security guard", default=False)

    instant_book = models.BooleanField(default=False, help_text="Confirm bookings automatically, no approval needed.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    AMENITIES = [
        ("is_covered", "Covered", "fa-umbrella"),
        ("has_cctv", "CCTV", "fa-video"),
        ("has_ev_charging", "EV charging", "fa-charging-station"),
        ("has_guard", "Guarded", "fa-user-shield"),
    ]

    @property
    def amenities(self):
        return [(label, icon) for field, label, icon in self.AMENITIES if getattr(self, field)]

    def accepts(self, vehicle_type):
        return self.accepts_car if vehicle_type == "car" else self.accepts_bike

    def overlapping(self, start, end, statuses=None, exclude_id=None):
        qs = self.bookings.filter(
            status__in=statuses or [Booking.PENDING, Booking.CONFIRMED],
            start__lt=end,
            end__gt=start,
        )
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        return qs

    def free_slots(self, start, end, statuses=None, exclude_id=None):
        return max(self.capacity - self.overlapping(start, end, statuses, exclude_id).count(), 0)

    def free_now(self):
        now = timezone.now()
        return self.free_slots(now, now + timezone.timedelta(minutes=1), [Booking.CONFIRMED])

    def rating_summary(self):
        return Review.objects.filter(booking__spot=self).aggregate(avg=Avg("rating"), count=Count("id"))

    def directions_url(self):
        return f"https://www.google.com/maps/dir/?api=1&destination={self.latitude},{self.longitude}"


class Booking(models.Model):
    PENDING, CONFIRMED, REJECTED, CANCELLED = "pending", "confirmed", "rejected", "cancelled"
    STATUS_CHOICES = [
        (PENDING, "Awaiting approval"),
        (CONFIRMED, "Confirmed"),
        (REJECTED, "Declined"),
        (CANCELLED, "Cancelled"),
    ]

    parker = models.ForeignKey(Parker, on_delete=models.CASCADE, related_name="bookings")
    spot = models.ForeignKey(ParkingSpot, on_delete=models.CASCADE, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    vehicle_type = models.CharField(max_length=10, choices=Parker.VEHICLE_CHOICES)
    vehicle_number = models.CharField(max_length=20)
    total_price = models.DecimalField(max_digits=9, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start"]

    def __str__(self):
        return f"{self.code} · {self.spot}"

    @property
    def code(self):
        return f"PM-{self.pk:05d}"

    @property
    def hours(self):
        return round((self.end - self.start).total_seconds() / 3600)

    @property
    def phase(self):
        """What the parker/landlord should see: upcoming, active, completed, or the terminal status."""
        if self.status != self.CONFIRMED:
            return self.status
        now = timezone.now()
        if now < self.start:
            return "upcoming"
        if now < self.end:
            return "active"
        return "completed"

    @property
    def can_cancel(self):
        return self.status in (self.PENDING, self.CONFIRMED) and timezone.now() < self.start

    @property
    def can_review(self):
        return self.phase == "completed" and not hasattr(self, "review")


class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=600)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating}★ for {self.booking.spot}"
