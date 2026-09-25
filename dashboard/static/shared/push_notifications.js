(() => {
    const button = document.getElementById("dvGlobalPushToggle");
    if (!button) return;

    const label = button.querySelector("[data-push-label]");
    const csrf = document.querySelector(
        "#dvGlobalPushCsrf input[name=csrfmiddlewaretoken]"
    )?.value || "";

    const base64ToUint8 = (value) => {
        const padding = "=".repeat((4 - value.length % 4) % 4);
        const base64 = (value + padding)
            .replace(/-/g, "+")
            .replace(/_/g, "/");
        const raw = window.atob(base64);
        return Uint8Array.from(
            [...raw].map((char) => char.charCodeAt(0))
        );
    };

    const setState = (state) => {
        const active = state === "active";
        const blocked = state === "blocked";

        button.classList.toggle("is-active", active);
        button.classList.toggle("is-blocked", blocked);
        button.setAttribute("aria-pressed", active ? "true" : "false");

        if (label) {
            label.textContent = active
                ? "Avisos activos"
                : blocked
                    ? "Avisos bloqueados"
                    : "Activar avisos";
        }

        button.setAttribute(
            "aria-label",
            active
                ? "Desactivar notificaciones"
                : blocked
                    ? "Notificaciones bloqueadas"
                    : "Activar notificaciones"
        );
    };

    const post = async (url, payload) => {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
            },
            body: JSON.stringify(payload || {}),
        });

        if (!response.ok) {
            let message = "No pudimos guardar la configuración.";
            try {
                const data = await response.json();
                message = data.mensaje || message;
            } catch (error) {}
            throw new Error(message);
        }

        return response.json();
    };

    const getRegistration = () =>
        navigator.serviceWorker.register(
            button.dataset.worker,
            { scope: "/gestion/" }
        );

    const notifyPermissionHelp = () => {
        const message =
            "Android bloqueó el permiso de notificaciones porque hay una " +
            "burbuja, ventana flotante o superposición activa. Cerrá esas " +
            "superposiciones (por ejemplo barra lateral flotante, chat, " +
            "grabador o filtro de pantalla) y volvé a tocar Activar avisos.";

        if (window.DVToast?.warning) {
            window.DVToast.warning(message);
        } else {
            button.title = message;
        }
    };

    const syncState = async () => {
        if (
            !("serviceWorker" in navigator)
            || !("PushManager" in window)
            || !("Notification" in window)
        ) {
            button.disabled = true;
            button.title = "Este navegador no admite notificaciones push";
            setState("inactive");
            return;
        }

        if (Notification.permission === "denied") {
            button.title = "Habilitá las notificaciones desde los permisos del navegador";
            setState("blocked");
            return;
        }

        try {
            const registration = await getRegistration();
            const subscription =
                await registration.pushManager.getSubscription();
            setState(subscription ? "active" : "inactive");
            button.title = subscription
                ? "Notificaciones activas"
                : "Activar notificaciones";
        } catch (error) {
            button.disabled = true;
            button.title = "No pudimos iniciar las notificaciones";
        }
    };

    button.addEventListener("click", async () => {
        button.disabled = true;

        try {
            const registration = await getRegistration();
            let subscription =
                await registration.pushManager.getSubscription();

            if (subscription) {
                const endpoint = subscription.endpoint;
                await subscription.unsubscribe();
                await post(button.dataset.unsubscribe, { endpoint });
                setState("inactive");
                button.title = "Activar notificaciones";
                return;
            }

            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                setState(
                    permission === "denied" ? "blocked" : "inactive"
                );
                button.title = permission === "denied"
                    ? "Habilitá las notificaciones desde los permisos del navegador"
                    : "Activar notificaciones";
                notifyPermissionHelp();
                return;
            }

            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: base64ToUint8(
                    button.dataset.publicKey
                ),
            });

            await post(
                button.dataset.subscribe,
                subscription.toJSON()
            );

            setState("active");
            button.title = "Notificaciones activas";
        } catch (error) {
            setState("inactive");
            button.title = error.message || "No pudimos activar los avisos";

            if (
                Notification.permission !== "granted"
            ) {
                notifyPermissionHelp();
            } else if (window.DVToast?.error) {
                window.DVToast.error(
                    error.message || "No pudimos activar los avisos."
                );
            }
        } finally {
            button.disabled = false;
        }
    });

    syncState();
})();
