from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import Booking, ParkingSpot, Review

INPUT = "pm-input"
DURATION_CHOICES = [(h, f"{h} hour{'s' if h > 1 else ''}") for h in (1, 2, 3, 4, 6, 8, 12, 24)]


class SpotForm(forms.ModelForm):
    class Meta:
        model = ParkingSpot
        fields = [
            "title", "description", "address", "city", "latitude", "longitude", "photo",
            "hourly_rate", "capacity", "accepts_car", "accepts_bike",
            "is_covered", "has_cctv", "has_ev_charging", "has_guard", "instant_book",
        ]
        labels = {
            "title": "Listing title",
            "hourly_rate": "Price per hour (₹)",
            "capacity": "Number of slots",
            "accepts_car": "Cars",
            "accepts_bike": "Bikes",
            "instant_book": "Instant book",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT, "placeholder": "Covered driveway near Anna Nagar Tower"}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 3, "placeholder": "Gate code, access hours, how to find the spot…"}),
            "address": forms.TextInput(attrs={"class": INPUT, "placeholder": "12, 3rd Main Road, Anna Nagar"}),
            "city": forms.TextInput(attrs={"class": INPUT, "placeholder": "Chennai"}),
            "latitude": forms.HiddenInput,
            "longitude": forms.HiddenInput,
            "photo": forms.FileInput(attrs={"class": "pm-file", "accept": "image/*"}),
            "hourly_rate": forms.NumberInput(attrs={"class": INPUT, "min": 1, "step": 5}),
            "capacity": forms.NumberInput(attrs={"class": INPUT, "min": 1, "max": 500}),
        }
        error_messages = {
            "latitude": {"required": "Drop a pin on the map to set the location."},
            "longitude": {"required": "Drop a pin on the map to set the location."},
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("accepts_car") and not cleaned.get("accepts_bike"):
            raise forms.ValidationError("Accept at least one vehicle type.")
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if lat is not None and not -90 <= lat <= 90 or lng is not None and not -180 <= lng <= 180:
            raise forms.ValidationError("That map location isn't valid.")
        return cleaned


class BookingForm(forms.Form):
    start = forms.DateTimeField(
        label="Arrive",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"class": INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    hours = forms.TypedChoiceField(
        label="Duration", choices=DURATION_CHOICES, coerce=int, initial=2,
        widget=forms.Select(attrs={"class": INPUT}),
    )

    def __init__(self, *args, spot, parker, **kwargs):
        self.spot, self.parker = spot, parker
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            soon = timezone.localtime() + timedelta(minutes=30)
            self.initial["start"] = soon.replace(minute=0 if soon.minute < 30 else 30, second=0, microsecond=0)

    def clean(self):
        cleaned = super().clean()
        start, hours = cleaned.get("start"), cleaned.get("hours")
        if not start or not hours:
            return cleaned
        if start < timezone.now() - timedelta(minutes=5):
            raise forms.ValidationError("Pick a start time in the future.")
        if start > timezone.now() + timedelta(days=60):
            raise forms.ValidationError("Bookings can be made up to 60 days ahead.")
        if not self.spot.is_active:
            raise forms.ValidationError("This spot isn't taking bookings right now.")
        if not self.spot.accepts(self.parker.vehicle_type):
            raise forms.ValidationError(f"This spot doesn't accept {self.parker.get_vehicle_type_display().lower()}s.")
        end = start + timedelta(hours=hours)
        if self.parker.bookings.filter(
            status__in=[Booking.PENDING, Booking.CONFIRMED], start__lt=end, end__gt=start
        ).exists():
            raise forms.ValidationError("You already have a booking during this time.")
        if self.spot.free_slots(start, end) == 0:
            raise forms.ValidationError("Fully booked for that time. Try another slot or a nearby spot.")
        cleaned["end"] = end
        return cleaned

    def save(self):
        d = self.cleaned_data
        return Booking.objects.create(
            parker=self.parker,
            spot=self.spot,
            start=d["start"],
            end=d["end"],
            vehicle_type=self.parker.vehicle_type,
            vehicle_number=self.parker.vehicle_number,
            total_price=self.spot.hourly_rate * d["hours"],
            status=Booking.CONFIRMED if self.spot.instant_book else Booking.PENDING,
        )


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.HiddenInput,
            "comment": forms.Textarea(attrs={"class": INPUT, "rows": 2, "placeholder": "How was the spot? (optional)"}),
        }
