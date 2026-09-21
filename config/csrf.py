from django.shortcuts import redirect, render
from django.urls import reverse


def csrf_failure(request, reason=""):
    login_path = reverse("login")

    # Caso observado en mobile: el primer POST del login ya autenticó al
    # usuario y un segundo tap reenvió el formulario con el token anterior.
    # Si la sesión ya está autenticada, continuar a Gestión es más correcto
    # que mostrar un 403 por ese segundo envío obsoleto.
    if (
        request.path == login_path
        and getattr(request, "user", None)
        and request.user.is_authenticated
    ):
        return redirect("dashboard:inicio")

    return render(
        request,
        "registration/csrf_error.html",
        {
            "login_url": login_path,
        },
        status=403,
    )
