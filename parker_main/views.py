from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from Authentication.auth import current_user, landlord_required, parker_required

from .forms import BookingForm, ReviewForm, SpotForm
from .illustrations import ensure_photo
from .models import Booking, ParkingSpot, Review, haversine

DEFAULT_CENTER = (13.0827, 80.2707)  # Chennai
RADIUS_CHOICES = [1, 2, 5, 10, 25]
SORTS = {"distance": "Nearest", "price": "Cheapest", "rating": "Top rated"}


def _float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- parker

def _current_parker(request):
    role, user = current_user(request)
    return user if role == "parker" else None


def Parker_main(request):
    """Map + list search for nearby spots. Public, so visitors can browse before signing up."""
    parker = _current_parker(request)
    g = request.GET
    lat, lon = _float(g.get("lat"), DEFAULT_CENTER[0]), _float(g.get("lon"), DEFAULT_CENTER[1])
    radius = int(_float(g.get("radius"), 10)) if int(_float(g.get("radius"), 10)) in RADIUS_CHOICES else 10
    max_price = _float(g.get("max_price"), None)
    vehicle = g.get("vehicle") or (parker.vehicle_type if parker else "car")
    sort = g.get("sort") if g.get("sort") in SORTS else "distance"
    wanted = [f for f, _, _ in ParkingSpot.AMENITIES if g.get(f)]
    instant = bool(g.get("instant_book"))

    spots = ParkingSpot.objects.filter(is_active=True).annotate(
        avg_rating=Avg("bookings__review__rating"), review_count=Count("bookings__review"),
    )
    spots = spots.filter(accepts_car=True) if vehicle == "car" else spots.filter(accepts_bike=True)
    if max_price:
        spots = spots.filter(hourly_rate__lte=max_price)
    for field in wanted:
        spots = spots.filter(**{field: True})
    if instant:
        spots = spots.filter(instant_book=True)

    # Cheap bounding box before the exact distance check.
    dlat = radius / 111.0
    spots = spots.filter(latitude__range=(lat - dlat, lat + dlat), longitude__range=(lon - dlat * 1.2, lon + dlat * 1.2))

    results = []
    for spot in spots:
        spot.distance = haversine(lat, lon, spot.latitude, spot.longitude)
        if spot.distance <= radius:
            results.append(spot)
    sort_key = {
        "distance": lambda s: s.distance,
        "price": lambda s: (s.hourly_rate, s.distance),
        "rating": lambda s: (-(s.avg_rating or 0), s.distance),
    }[sort]
    results.sort(key=sort_key)
    total = len(results)
    results = results[:60]

    map_data = [{
        "id": s.id, "lat": s.latitude, "lng": s.longitude, "title": s.title,
        "price": int(s.hourly_rate), "url": f"/parker/spots/{s.id}/",
    } for s in results]

    return render(request, "parker/find.html", {
        "spots": results,
        "total": total,
        "map_data": map_data,
        "center": {"lat": lat, "lng": lon, "radius": radius},
        "radius_choices": RADIUS_CHOICES,
        "sorts": SORTS,
        "sort": sort,
        "sort_label": SORTS[sort],
        "vehicle": vehicle,
        "max_price": g.get("max_price", ""),
        "amenity_filters": [(f, label, icon, f in wanted) for f, label, icon in ParkingSpot.AMENITIES],
        "instant": instant,
        "has_location": "lat" in g,
        "upcoming": parker and parker.bookings.filter(status=Booking.CONFIRMED, end__gt=timezone.now()).select_related("spot").order_by("start").first(),
    })


def spot_detail(request, spot_id):
    """Public spot page; booking (POST) needs a parker account."""
    spot = get_object_or_404(ParkingSpot.objects.select_related("landlord"), pk=spot_id)
    parker = _current_parker(request)
    if request.method == "POST" and not parker:
        messages.info(request, "Log in as a parker, or try the demo, to book this spot.")
        return redirect(f"{reverse('login')}?{urlencode({'role': 'parker', 'next': request.path})}")
    if request.method == "POST":
        form = BookingForm(request.POST, spot=spot, parker=parker)
        if form.is_valid():
            with transaction.atomic():
                booking = form.save()
            if booking.status == Booking.CONFIRMED:
                messages.success(request, f"You're booked! Your pass {booking.code} is ready.")
            else:
                messages.success(request, f"Request sent to {spot.landlord.name.split()[0]}. We'll show it here once they respond.")
            return redirect("parker_bookings")
    else:
        form = BookingForm(spot=spot, parker=parker) if parker else None

    return render(request, "parker/spot_detail.html", {
        "spot": spot,
        "form": form,
        "rating": spot.rating_summary(),
        "reviews": Review.objects.filter(booking__spot=spot).select_related("booking__parker")[:10],
        "free_now": spot.free_now(),
        "accepts_my_vehicle": spot.accepts(parker.vehicle_type) if parker else True,
    })


def spot_directions(request, spot_id):
    """In-app turn-by-turn directions to a spot (routing runs in the browser via OSRM). Public, like the spot page."""
    spot = get_object_or_404(ParkingSpot.objects.select_related("landlord"), pk=spot_id)
    parker = _current_parker(request)
    booking = None
    if parker:
        booking = parker.bookings.filter(spot=spot, status=Booking.CONFIRMED, end__gt=timezone.now()).order_by("start").first()
    return render(request, "parker/directions.html", {
        "spot": spot,
        "booking": booking,
        "dest": {"lat": spot.latitude, "lng": spot.longitude, "title": spot.title},
    })


@parker_required
def parker_bookings(request):
    bookings = list(request.pm_user.bookings.select_related("spot", "spot__landlord", "review"))
    groups = {"now": [], "pending": [], "past": []}
    for b in bookings:
        if b.phase in ("active", "upcoming"):
            groups["now"].append(b)
        elif b.phase == Booking.PENDING:
            groups["pending"].append(b)
        else:
            groups["past"].append(b)
    groups["now"].sort(key=lambda b: b.start)
    return render(request, "parker/bookings.html", {"groups": groups, "review_form": ReviewForm()})


@parker_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, parker=request.pm_user)
    if booking.can_cancel:
        booking.status = Booking.CANCELLED
        booking.save(update_fields=["status"])
        messages.success(request, f"Booking {booking.code} cancelled.")
    else:
        messages.error(request, "This booking can no longer be cancelled.")
    return redirect("parker_bookings")


@parker_required
@require_POST
def review_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, parker=request.pm_user)
    if not booking.can_review:
        messages.error(request, "You can review a spot after your booking ends.")
        return redirect("parker_bookings")
    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.booking = booking
        review.save()
        messages.success(request, "Thanks for the review!")
    else:
        messages.error(request, "Pick a star rating from 1 to 5.")
    return redirect("parker_bookings")


# ---------------------------------------------------------------- landlord

@landlord_required
def landlord_dashboard(request):
    landlord = request.pm_user
    now = timezone.now()
    today = timezone.localdate()
    bookings = Booking.objects.filter(spot__landlord=landlord).select_related("spot", "parker")
    confirmed = bookings.filter(status=Booking.CONFIRMED)

    # Booked revenue per day for the last 14 days, by booking start date.
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day = {d: 0 for d in days}
    for b in confirmed.filter(start__date__gte=days[0], start__date__lte=today):
        d = timezone.localtime(b.start).date()
        if d in per_day:
            per_day[d] += float(b.total_price)
    peak = max(per_day.values()) or 1
    chart = [{"date": d, "value": v, "pct": round(v / peak * 100, 1)} for d, v in per_day.items()]

    month_start = today.replace(day=1)
    spots = landlord.spots.annotate(
        avg_rating=Avg("bookings__review__rating"),
        review_count=Count("bookings__review", distinct=True),
        upcoming_count=Count("bookings", filter=Q(bookings__status=Booking.CONFIRMED, bookings__end__gt=now), distinct=True),
    )

    return render(request, "landlord/dashboard.html", {
        "spots": spots,
        "requests": bookings.filter(status=Booking.PENDING, start__gt=now).order_by("start"),
        "upcoming": confirmed.filter(end__gt=now).order_by("start")[:8],
        "stats": {
            "month_revenue": confirmed.filter(start__date__gte=month_start).aggregate(s=Sum("total_price"))["s"] or 0,
            "total_revenue": confirmed.aggregate(s=Sum("total_price"))["s"] or 0,
            "active_now": confirmed.filter(start__lte=now, end__gt=now).count(),
            "rating": Review.objects.filter(booking__spot__landlord=landlord).aggregate(a=Avg("rating"), c=Count("id")),
        },
        "chart": chart,
        "chart_total": sum(per_day.values()),
    })


@landlord_required
def spot_create(request):
    return _spot_form(request, ParkingSpot(landlord=request.pm_user, city=request.pm_user.city))


@landlord_required
def spot_edit(request, spot_id):
    return _spot_form(request, get_object_or_404(ParkingSpot, pk=spot_id, landlord=request.pm_user))


def _spot_form(request, spot):
    is_new = spot.pk is None
    if request.method == "POST":
        form = SpotForm(request.POST, request.FILES, instance=spot)
        if form.is_valid():
            spot = form.save()
            ensure_photo(spot)
            messages.success(request, "Your spot is live on the map!" if is_new else "Spot updated.")
            return redirect("landlord_dashboard")
    else:
        form = SpotForm(instance=spot)
    return render(request, "landlord/spot_form.html", {"form": form, "spot": spot, "is_new": is_new})


@landlord_required
@require_POST
def spot_toggle(request, spot_id):
    spot = get_object_or_404(ParkingSpot, pk=spot_id, landlord=request.pm_user)
    spot.is_active = not spot.is_active
    spot.save(update_fields=["is_active"])
    messages.success(request, f"“{spot.title}” is now {'live' if spot.is_active else 'paused'}.")
    return redirect("landlord_dashboard")


@landlord_required
@require_POST
def booking_respond(request, booking_id, action):
    booking = get_object_or_404(Booking, pk=booking_id, spot__landlord=request.pm_user, status=Booking.PENDING)
    if action == "accept":
        with transaction.atomic():
            if booking.spot.free_slots(booking.start, booking.end, [Booking.CONFIRMED], exclude_id=booking.pk) == 0:
                messages.error(request, "No free slot left for that time. Decline it or add capacity.")
                return redirect("landlord_dashboard")
            booking.status = Booking.CONFIRMED
            booking.save(update_fields=["status"])
        messages.success(request, f"Accepted {booking.parker.name}'s booking.")
    elif action == "decline":
        booking.status = Booking.REJECTED
        booking.save(update_fields=["status"])
        messages.success(request, f"Declined {booking.parker.name}'s request.")
    return redirect("landlord_dashboard")


@landlord_required
def landlord_bookings(request):
    bookings = Booking.objects.filter(spot__landlord=request.pm_user).select_related("spot", "parker", "review")
    status = request.GET.get("status", "")
    if status in dict(Booking.STATUS_CHOICES):
        bookings = bookings.filter(status=status)
    return render(request, "landlord/bookings.html", {
        "bookings": bookings[:200],
        "status": status,
        "statuses": Booking.STATUS_CHOICES,
    })
