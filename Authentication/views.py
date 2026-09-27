import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, Sum
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from parker_main.models import Booking, ParkingSpot, Review

from . import auth
from .demo import demo_accounts
from .forms import LandlordSignUpForm, ParkerSignUpForm
from .models import Landlord, Parker, normalize_phone

HOME_FOR_ROLE = {"parker": "Parker_main", "landlord": "landlord_dashboard"}


@lru_cache(maxsize=1)
def _test_count():
    """Number of automated tests (shown on the landing page).

    deploy/build.py records pytest's collected count; without it, count the test functions in the source.
    """
    root = Path(settings.BASE_DIR)
    recorded = root / "deploy" / "test_count.txt"
    if recorded.exists():
        return int(recorded.read_text().strip())
    files = [*root.glob("*/tests.py"), *root.glob("tests/test_*.py")]
    return sum(len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8"), re.M)) for f in files)


def home(request):
    chennai = ParkingSpot.objects.filter(is_active=True, landlord__phone__startswith="91000")
    return render(request, "home.html", {
        "location_count": chennai.count(),
        "test_count": _test_count(),
        "map_spots": [
            {"lat": s.latitude, "lng": s.longitude, "price": int(s.hourly_rate), "url": f"/parker/spots/{s.id}/"}
            for s in chennai.only("latitude", "longitude", "hourly_rate")
        ],
        "featured": ParkingSpot.objects.filter(is_active=True, city__iexact="Chennai", landlord__phone__startswith="91000")
            .exclude(photo="").annotate(avg_rating=Avg("bookings__review__rating"), review_count=Count("bookings__review"))
            .filter(review_count__gte=2).order_by("-avg_rating", "-review_count")[:4],
        "reviews": Review.objects.select_related("booking__spot", "booking__parker").filter(rating__gte=4)[:3],
    })


def login_view(request):
    role = request.POST.get("role") or request.GET.get("role") or "parker"
    if role not in auth.ROLES:
        role = "parker"
    next_url = request.POST.get("next") or request.GET.get("next") or ""

    if request.method == "POST":
        phone = normalize_phone(request.POST.get("phone"))
        pin = "".join(request.POST.get(f"pin{i}", "").strip() for i in range(1, 5))

        if not phone or len(pin) != 4:
            messages.error(request, "Enter your phone number and 4-digit PIN.")
        elif auth.is_locked_out(role, phone):
            messages.error(request, "Too many wrong attempts. Try again in 5 minutes.")
        else:
            user = auth.ROLES[role].objects.filter(phone=phone).first()
            if user and user.check_pin(pin):
                auth.clear_failures(role, phone)
                auth.login_as(request, role, user)
                messages.success(request, f"Welcome back, {user.name.split()[0]}!")
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect(HOME_FOR_ROLE[role])
            auth.record_failure(role, phone)
            messages.error(request, "That phone number and PIN don't match.")

    return render(request, "auth/login.html", {"role": role, "next": next_url, "phone": request.POST.get("phone", "")})


@require_POST
def demo_login(request, role):
    """Log straight into a demo account (no sign-up) so anyone can explore both sides of the app."""
    if not settings.DEMO_MODE or role not in auth.ROLES:
        raise Http404
    user = demo_accounts()[role]
    auth.login_as(request, role, user)
    messages.success(request, "You're exploring the demo " + ("driver" if role == "parker" else "host")
                     + " account. It's all sample data, so click around freely.")
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(HOME_FOR_ROLE[role])


def logout_view(request):
    if request.method == "POST":
        auth.logout(request)
        messages.success(request, "You've been logged out.")
    return redirect("home")


def _signup(request, role, form_class, template):
    if request.method == "POST":
        form = form_class(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            auth.login_as(request, role, user)
            messages.success(request, f"Welcome to ParkMatch, {user.name.split()[0]}!")
            return redirect(HOME_FOR_ROLE[role])
    else:
        form = form_class()
    return render(request, template, {"form": form})


def parker_sign_up(request):
    return _signup(request, "parker", ParkerSignUpForm, "auth/signup_parker.html")


def landlord_signup(request):
    return _signup(request, "landlord", LandlordSignUpForm, "auth/signup_landlord.html")


@staff_member_required
def dashboard_view(request):
    return render(request, "dashboard.html", {
        "parkers": Parker.objects.all(),
        "landlords": Landlord.objects.annotate(spot_count=Count("spots")).order_by("-spot_count", "name"),
        "spot_count": ParkingSpot.objects.count(),
        "bookings": Booking.objects.select_related("parker", "spot")[:20],
        "booking_count": Booking.objects.count(),
        "revenue": Booking.objects.filter(status=Booking.CONFIRMED).aggregate(s=Sum("total_price"))["s"] or 0,
    })
