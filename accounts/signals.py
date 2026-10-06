from django.contrib import messages
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


@receiver(user_logged_in)
def _welcome(sender, request, user, **kwargs):
    if request is None:
        return
    messages.info(request, f"Welcome back, {user.get_short_name() or user.username}.", fail_silently=True)


@receiver(user_logged_out)
def _bye(sender, request, user, **kwargs):
    if request is not None:
        messages.add_message(request, messages.SUCCESS, "You have been logged out safely.", extra_tags="Logged out", fail_silently=True)
