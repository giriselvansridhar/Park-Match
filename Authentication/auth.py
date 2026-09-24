"""Session-based login for the two roles (parker, landlord), kept separate from Django's staff auth."""
from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from .models import Landlord, Parker

ROLES = {"parker": Parker, "landlord": Landlord}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 5 * 60


def login_as(request, role, user):
    request.session.cycle_key()
    request.session["role"] = role
    request.session["user_id"] = user.pk


def logout(request):
    request.session.flush()


def current_user(request):
    if not hasattr(request, "_pm_user"):
        role = request.session.get("role")
        model = ROLES.get(role)
        user = model.objects.filter(pk=request.session.get("user_id")).first() if model else None
        request._pm_user = (role, user) if user else (None, None)
    return request._pm_user


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            current_role, user = current_user(request)
            if current_role != role:
                messages.info(request, f"Please log in as a {role} to continue.")
                return redirect(f"{reverse('login')}?{urlencode({'role': role, 'next': request.get_full_path()})}")
            request.pm_user = user
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


parker_required = role_required("parker")
landlord_required = role_required("landlord")


def _attempt_key(role, phone):
    return f"pm-login-fail:{role}:{phone}"


def is_locked_out(role, phone):
    return cache.get(_attempt_key(role, phone), 0) >= MAX_ATTEMPTS


def record_failure(role, phone):
    key = _attempt_key(role, phone)
    cache.set(key, cache.get(key, 0) + 1, LOCKOUT_SECONDS)


def clear_failures(role, phone):
    cache.delete(_attempt_key(role, phone))


def user_context(request):
    """Template context processor: the signed-in role/user, plus demo/project info for the page chrome."""
    from django.conf import settings

    from .demo import is_demo

    role, user = current_user(request)
    return {
        "pm_role": role,
        "pm_user": user,
        "pm_is_demo": is_demo(user),
        "pm_demo_mode": settings.DEMO_MODE,
        "project_author": settings.PROJECT_AUTHOR,
        "project_repo_url": settings.PROJECT_REPO_URL,
    }
