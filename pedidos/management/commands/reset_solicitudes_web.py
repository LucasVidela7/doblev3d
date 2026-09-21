from django.core.management import BaseCommand

# Comando de mantenimiento controlado.
from django.core.management.color import no_style
from django.db import connection, transaction

from pedidos.models import SolicitudWeb


class Command(BaseCommand):
    help = (
        "Elimina todas las solicitudes web y reinicia su secuencia "
        "para que la próxima sea WEB0001."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            dest="confirm",
            default="",
            help="Debe ser exactamente RESET para ejecutar el borrado.",
        )

    def handle(self, *args, **options):
        if options.get("confirm") != "RESET":
            self.stderr.write(
                self.style.ERROR(
                    "Operación cancelada. Usá --confirm RESET."
                )
            )
            return

        with transaction.atomic():
            cantidad = SolicitudWeb.objects.count()
            SolicitudWeb.objects.all().delete()

            sql_list = connection.ops.sequence_reset_sql(
                no_style(),
                [SolicitudWeb],
            )
            with connection.cursor() as cursor:
                for sql in sql_list:
                    cursor.execute(sql)

        self.stdout.write(
            self.style.SUCCESS(
                f"WEB_REQUEST_RESET deleted={cantidad} next=WEB0001"
            )
        )
