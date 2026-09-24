"""One-click demo accounts, so visitors (e.g. recruiters) can explore both sides without signing up."""
from django.core.management import call_command

from .models import Landlord, Parker

DEMO_PARKER_PHONE = "9000000001"
DEMO_HOST_PHONE = "9000000002"
DEMO_PHONES = {DEMO_PARKER_PHONE, DEMO_HOST_PHONE}


def demo_accounts():
    """Returns {"parker": Parker, "landlord": Landlord}, seeding the demo data first if it's missing."""
    parker = Parker.objects.filter(phone=DEMO_PARKER_PHONE).first()
    host = Landlord.objects.filter(phone=DEMO_HOST_PHONE).first()
    if not parker or not host:
        call_command("seed_demo", verbosity=0)
    elif not _has_upcoming(host):
        # The seeded bookings are relative to when the data was made; refresh them once they're all in the past.
        call_command("seed_demo", reset=True, verbosity=0)
    return {"parker": Parker.objects.get(phone=DEMO_PARKER_PHONE), "landlord": Landlord.objects.get(phone=DEMO_HOST_PHONE)}


def _has_upcoming(host):
    from django.utils import timezone

    from parker_main.models import Booking
    return Booking.objects.filter(spot__landlord=host, status__in=[Booking.PENDING, Booking.CONFIRMED], start__gt=timezone.now()).exists()


def is_demo(user):
    return bool(user) and user.phone in DEMO_PHONES
