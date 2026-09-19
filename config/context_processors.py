from django.conf import settings


def webpush(request):
    public_key = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
    private_key = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    return {
        "webpush_habilitado": bool(public_key and private_key),
        "webpush_public_key": public_key,
    }
