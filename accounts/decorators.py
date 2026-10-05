from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(*roles):
    def decorator(view):
        @login_required(login_url='login')
        def wrapper(request, *args, **kwargs):
            prof = getattr(request.user, 'profile', None)
            ok = request.user.is_superuser or (prof and prof.role in roles)
            if not ok:
                messages.error(request, 'You do not have permission.')
                return redirect('dashboard')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator