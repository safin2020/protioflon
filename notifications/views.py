from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import Notification


@login_required
def notification_list(request):
    notifs = Notification.objects.filter(user=request.user)
    # সব unread কে read করে দিই
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'notifications/list.html', {'notifs': notifs})


@login_required
def mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save()
    if n.link:
        return redirect(n.link)
    return redirect('notification_list')


@login_required
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notification_list')


@login_required
def unread_count_api(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})