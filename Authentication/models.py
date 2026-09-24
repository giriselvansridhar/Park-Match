import re

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import models


def normalize_phone(raw):
    """Digits only; drops a leading 91 country code from 12-digit Indian numbers."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def is_hashed(value):
    try:
        identify_hasher(value)
        return True
    except ValueError:
        return False


class PinMixin:
    """Stores the 4-digit PIN hashed, and upgrades any legacy plain-text PIN on login."""

    def set_pin(self, raw_pin):
        self.pin = make_password(raw_pin)

    def check_pin(self, raw_pin):
        if is_hashed(self.pin):
            return check_password(raw_pin, self.pin)
        if self.pin == raw_pin:
            self.set_pin(raw_pin)
            self.save(update_fields=["pin"])
            return True
        return False


class Parker(PinMixin, models.Model):
    VEHICLE_CHOICES = [('car', 'Car'), ('bike', 'Bike')]

    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    vehicle_type = models.CharField(max_length=10, choices=VEHICLE_CHOICES, default="car")
    vehicle_number = models.CharField(max_length=20, unique=True)
    pin = models.CharField(max_length=128)
    registered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.vehicle_type})"


class Landlord(PinMixin, models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    pincode = models.CharField(max_length=10, blank=True, default="")
    address = models.TextField(blank=True, default="")
    area = models.CharField(max_length=255, blank=True, default="")
    landmark = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="India")
    pin = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=12, decimal_places=10, null=True, blank=True)
    longitude = models.DecimalField(max_digits=13, decimal_places=10, null=True, blank=True)
    profile_image = models.ImageField(upload_to='landlord_images/', null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.name
