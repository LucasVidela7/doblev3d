from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from productos.models import Producto
from pedidos.models import (
    Pedido,
    DetallePedido,
    DetalleKitProducto,
    EstadoImpresionPedido,
)


ESTADOS_ACTIVOS = [
    "PENDIENTE",
    "PREPARANDO",
    "LISTO",
]


class Command(BaseCommand):
    help = (
        "Reemplaza un producto por otro dentro de pedidos activos "
        "(PENDIENTE, PREPARANDO y LISTO). "
        "Por defecto solo simula. Use --confirmar para aplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "producto_origen",
            type=str,
            help="Nombre exacto del producto que será reemplazado.",
        )
        parser.add_argument(
            "producto_destino",
            type=str,
            help="Nombre exacto del producto que reemplazará al origen.",
        )
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Aplica realmente los cambios. Sin esta opción solo simula.",
        )

    def _buscar_producto(self, nombre, etiqueta):
        qs = Producto.objects.filter(nombre__iexact=nombre.strip())

        cantidad = qs.count()

        if cantidad == 0:
            raise CommandError(
                f"No se encontró el producto {etiqueta}: {nombre!r}"
            )

        if cantidad > 1:
            coincidencias = ", ".join(
                f"{p.codigo} - {p.nombre}"
                for p in qs.order_by("id")
            )
            raise CommandError(
                f"Hay más de un producto que coincide con {nombre!r}: "
                f"{coincidencias}. Renombrá temporalmente uno o usá un "
                "nombre único antes de ejecutar el comando."
            )

        return qs.first()

    def _pedidos_afectados(self, origen):
        ids = set()

        # Detalles de producto y personalizados.
        ids.update(
            DetallePedido.objects.filter(
                pedido__estado__in=ESTADOS_ACTIVOS,
                producto=origen,
            ).values_list("pedido_id", flat=True)
        )

        # Componentes de kits.
        ids.update(
            DetalleKitProducto.objects.filter(
                detalle__pedido__estado__in=ESTADOS_ACTIVOS,
                producto=origen,
            ).values_list("detalle__pedido_id", flat=True)
        )

        # Por seguridad, también contemplamos estados operativos antiguos.
        ids.update(
            EstadoImpresionPedido.objects.filter(
                pedido__estado__in=ESTADOS_ACTIVOS,
                producto=origen,
            ).values_list("pedido_id", flat=True)
        )

        return sorted(ids)

    def _resumen(self, origen, destino, pedidos_ids):
        detalles_producto = DetallePedido.objects.filter(
            pedido_id__in=pedidos_ids,
            producto=origen,
            tipo_item="PRODUCTO",
        )

        detalles_personalizados = DetallePedido.objects.filter(
            pedido_id__in=pedidos_ids,
            producto=origen,
            tipo_item="PERSONALIZADO",
        )

        componentes_kit = DetalleKitProducto.objects.filter(
            detalle__pedido_id__in=pedidos_ids,
            producto=origen,
        )

        estados_origen = EstadoImpresionPedido.objects.filter(
            pedido_id__in=pedidos_ids,
            producto=origen,
        )

        estados_destino = EstadoImpresionPedido.objects.filter(
            pedido_id__in=pedidos_ids,
            producto=destino,
        )

        return {
            "pedidos": len(pedidos_ids),
            "detalles_producto": detalles_producto.count(),
            "unidades_producto": sum(
                detalles_producto.values_list("cantidad", flat=True)
            ) or 0,
            "detalles_personalizados": detalles_personalizados.count(),
            "unidades_personalizadas": sum(
                detalles_personalizados.values_list("cantidad", flat=True)
            ) or 0,
            "componentes_kit": componentes_kit.count(),
            "unidades_kit": sum(
                componentes_kit.values_list("cantidad", flat=True)
            ) or 0,
            "estados_origen": estados_origen.count(),
            "estados_destino": estados_destino.count(),
            "listos_origen": estados_origen.filter(listo=True).count(),
            "listos_destino": estados_destino.filter(listo=True).count(),
        }

    def _mostrar_resumen(
        self,
        origen,
        destino,
        pedidos_ids,
        resumen,
        confirmar,
    ):
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "REEMPLAZO DE PRODUCTO"
            )
        )
        self.stdout.write(
            f"Origen : {origen.codigo} - {origen.nombre}"
        )
        self.stdout.write(
            f"Destino: {destino.codigo} - {destino.nombre}"
        )
        self.stdout.write("")
        self.stdout.write(
            "Se modificarán únicamente pedidos activos: "
            "PENDIENTE, PREPARANDO y LISTO."
        )
        self.stdout.write(
            "ENTREGADOS y CANCELADOS no se modifican."
        )
        self.stdout.write("")
        self.stdout.write(
            f"Pedidos afectados             : {resumen['pedidos']}"
        )
        self.stdout.write(
            f"Detalles PRODUCTO             : "
            f"{resumen['detalles_producto']} "
            f"({resumen['unidades_producto']} unidades)"
        )
        self.stdout.write(
            f"Detalles PERSONALIZADO        : "
            f"{resumen['detalles_personalizados']} "
            f"({resumen['unidades_personalizadas']} unidades)"
        )
        self.stdout.write(
            f"Componentes dentro de KIT     : "
            f"{resumen['componentes_kit']} "
            f"({resumen['unidades_kit']} unidades)"
        )
        self.stdout.write(
            f"Estados LISTO del origen      : "
            f"{resumen['listos_origen']}"
        )
        self.stdout.write(
            f"Estados LISTO del destino     : "
            f"{resumen['listos_destino']}"
        )
        self.stdout.write("")

        if pedidos_ids:
            codigos = list(
                Pedido.objects.filter(id__in=pedidos_ids)
                .order_by("fecha_entrega", "id")
                .values_list("id", flat=True)
            )
            self.stdout.write(
                "Pedidos: "
                + ", ".join(
                    f"PED{pedido_id:04d}"
                    for pedido_id in codigos
                )
            )
            self.stdout.write("")

        if not confirmar:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se realizó ningún cambio."
                )
            )
            self.stdout.write(
                "Si el resumen es correcto, ejecutá nuevamente "
                "agregando --confirmar."
            )

    def _restaurar_y_borrar_estado(
        self,
        pedido,
        producto,
    ):
        """
        Si ese producto estaba LISTO, devuelve exactamente el stock que
        había sido descontado y elimina su EstadoImpresionPedido.

        Se elimina el estado porque después del reemplazo cambia la demanda
        del pedido y debe volver a calcularse desde PENDIENTE.
        """
        estado = (
            EstadoImpresionPedido.objects
            .select_for_update()
            .filter(
                pedido=pedido,
                producto=producto,
            )
            .first()
        )

        if not estado:
            return 0

        cantidad_restaurada = 0

        if (
            estado.stock_descontado
            and estado.cantidad_stock_descontada > 0
        ):
            producto_bloqueado = (
                Producto.objects
                .select_for_update()
                .get(id=producto.id)
            )

            cantidad_restaurada = (
                estado.cantidad_stock_descontada
            )

            producto_bloqueado.stock += cantidad_restaurada
            producto_bloqueado.save(
                update_fields=["stock"]
            )

        estado.delete()

        return cantidad_restaurada

    def _fusionar_componentes_kit(
        self,
        pedido,
        origen,
        destino,
    ):
        """
        Cambia componentes de kit ORIGEN -> DESTINO.

        Si el mismo detalle del kit ya contenía DESTINO, fusiona ambas
        cantidades para evitar dos filas equivalentes.
        """
        componentes_origen = list(
            DetalleKitProducto.objects
            .select_for_update()
            .filter(
                detalle__pedido=pedido,
                producto=origen,
            )
            .select_related("detalle")
        )

        modificados = 0

        for componente in componentes_origen:
            existente_destino = (
                DetalleKitProducto.objects
                .select_for_update()
                .filter(
                    detalle=componente.detalle,
                    producto=destino,
                )
                .exclude(id=componente.id)
                .first()
            )

            if existente_destino:
                existente_destino.cantidad += componente.cantidad
                existente_destino.save(
                    update_fields=["cantidad"]
                )
                componente.delete()
            else:
                componente.producto = destino
                componente.save(
                    update_fields=["producto"]
                )

            modificados += 1

        return modificados

    def _reemplazar_detalles(
        self,
        pedido,
        origen,
        destino,
    ):
        """
        Reemplaza PRODUCTO y PERSONALIZADO.

        No fusionamos DetallePedido PRODUCTO entre sí porque cada línea
        conserva su precio histórico. En la vista operativa se agrupan por
        producto igualmente.

        Los PERSONALIZADOS conservan su detalle/color/precio, pero cambian
        su producto base.
        """
        detalles = list(
            DetallePedido.objects
            .select_for_update()
            .filter(
                pedido=pedido,
                producto=origen,
            )
        )

        for detalle in detalles:
            detalle.producto = destino

            # Si era un personalizado LISTO, al cambiar de producto base
            # debe volver a PENDIENTE. No toca stock general.
            campos = ["producto"]

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.estado == "LISTO"
            ):
                detalle.estado = "PENDIENTE"
                campos.append("estado")

            detalle.save(update_fields=campos)

        return len(detalles)

    def _recalcular_estado_pedido(self, pedido):
        """
        Recalcula el estado general con la misma regla operativa:

        - nada listo -> PENDIENTE
        - algo listo -> PREPARANDO
        - todo listo -> LISTO

        Como los productos origen/destino afectados se resetean, los demás
        estados del pedido se conservan.
        """
        if pedido.estado in ["ENTREGADO", "CANCELADO"]:
            return

        estados_normales = (
            EstadoImpresionPedido.objects
            .filter(pedido=pedido)
        )

        cantidad_normales = estados_normales.count()
        normales_listos = (
            estados_normales
            .filter(listo=True)
            .count()
        )

        personalizados = (
            DetallePedido.objects
            .filter(
                pedido=pedido,
                tipo_item="PERSONALIZADO",
                producto__requiere_impresion=True,
                estado__in=["PENDIENTE", "LISTO"],
            )
        )

        cantidad_personalizados = personalizados.count()
        personalizados_listos = (
            personalizados
            .filter(estado="LISTO")
            .count()
        )

        cantidad_total = (
            cantidad_normales
            + cantidad_personalizados
        )

        cantidad_listos = (
            normales_listos
            + personalizados_listos
        )

        if (
            cantidad_total > 0
            and cantidad_total == cantidad_listos
        ):
            nuevo_estado = "LISTO"
        elif cantidad_listos > 0:
            nuevo_estado = "PREPARANDO"
        else:
            nuevo_estado = "PENDIENTE"

        if pedido.estado != nuevo_estado:
            pedido.estado = nuevo_estado
            pedido.save(update_fields=["estado"])

    def handle(self, *args, **options):
        origen = self._buscar_producto(
            options["producto_origen"],
            "origen",
        )

        destino = self._buscar_producto(
            options["producto_destino"],
            "destino",
        )

        if origen.id == destino.id:
            raise CommandError(
                "El producto origen y destino son el mismo."
            )

        pedidos_ids = self._pedidos_afectados(origen)
        resumen = self._resumen(
            origen,
            destino,
            pedidos_ids,
        )

        confirmar = options["confirmar"]

        self._mostrar_resumen(
            origen,
            destino,
            pedidos_ids,
            resumen,
            confirmar,
        )

        if not confirmar:
            return

        with transaction.atomic():
            # Bloqueamos los dos productos para proteger stock.
            origen = (
                Producto.objects
                .select_for_update()
                .get(id=origen.id)
            )
            destino = (
                Producto.objects
                .select_for_update()
                .get(id=destino.id)
            )

            total_stock_restaurado_origen = 0
            total_stock_restaurado_destino = 0
            total_detalles = 0
            total_componentes = 0

            for pedido_id in pedidos_ids:
                pedido = (
                    Pedido.objects
                    .select_for_update()
                    .get(id=pedido_id)
                )

                # La demanda tanto del origen como del destino cambia.
                # Para no mantener un LISTO parcial/inválido, reseteamos
                # ambos productos dentro de este pedido.
                total_stock_restaurado_origen += (
                    self._restaurar_y_borrar_estado(
                        pedido,
                        origen,
                    )
                )

                total_stock_restaurado_destino += (
                    self._restaurar_y_borrar_estado(
                        pedido,
                        destino,
                    )
                )

                total_detalles += self._reemplazar_detalles(
                    pedido,
                    origen,
                    destino,
                )

                total_componentes += (
                    self._fusionar_componentes_kit(
                        pedido,
                        origen,
                        destino,
                    )
                )

                self._recalcular_estado_pedido(pedido)

            # El producto origen NO se borra físicamente:
            # queda inactivo para conservar historial.
            if origen.activo:
                origen.activo = False
                origen.save(update_fields=["activo"])

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "REEMPLAZO COMPLETADO CORRECTAMENTE."
            )
        )
        self.stdout.write(
            f"Detalles modificados          : {total_detalles}"
        )
        self.stdout.write(
            f"Componentes de kit modificados: {total_componentes}"
        )
        self.stdout.write(
            f"Stock restaurado ORIGEN       : "
            f"{total_stock_restaurado_origen}"
        )
        self.stdout.write(
            f"Stock restaurado DESTINO      : "
            f"{total_stock_restaurado_destino}"
        )
        self.stdout.write(
            f"{origen.nombre} quedó INACTIVO."
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "Importante: no se transfirió el stock físico del "
                "producto origen al destino."
            )
        )
