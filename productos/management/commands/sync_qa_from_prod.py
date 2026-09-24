import io
import json
import os
import tarfile
import urllib.error
import urllib.request

import psycopg
from django.core.management.base import BaseCommand, CommandError
from psycopg import sql


class Command(BaseCommand):
    help = "Clona production hacia QA mediante un export HTTPS temporal y autenticado."

    def handle(self, *args, **options):
        env = (os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("APP_ENV") or "").strip().lower()
        if env != "qa":
            raise CommandError(f"Este comando solo puede ejecutarse en QA. Entorno detectado: {env!r}")

        source_url = (os.getenv("DB_SYNC_SOURCE_URL") or "").strip()
        token = (os.getenv("DB_SYNC_TOKEN") or "").strip()
        target_url = os.getenv("DATABASE_URL")
        if not source_url or not token or not target_url:
            raise CommandError("Faltan DB_SYNC_SOURCE_URL, DB_SYNC_TOKEN o DATABASE_URL.")
        if not source_url.startswith("https://") or "qa." in source_url or "-qa." in source_url:
            raise CommandError("DB_SYNC_SOURCE_URL no parece ser un endpoint HTTPS de producción.")

        request = urllib.request.Request(
            source_url,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "doblev3d-qa-db-sync/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise CommandError(f"El exportador respondió HTTP {response.status}.")
                bundle_bytes = response.read()
        except urllib.error.HTTPError as exc:
            raise CommandError(f"El exportador respondió HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise CommandError(f"No se pudo contactar al exportador de producción: {exc}.") from exc

        try:
            bundle = tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz")
            metadata_file = bundle.extractfile("metadata.json")
            if metadata_file is None:
                raise CommandError("El paquete no contiene metadata.json.")
            metadata = json.loads(metadata_file.read().decode("utf-8"))
        except (tarfile.TarError, json.JSONDecodeError, KeyError) as exc:
            raise CommandError(f"Paquete de producción inválido: {exc}.") from exc

        exported_tables = metadata.get("tables") or []
        exported_sequences = metadata.get("sequences") or []
        source_table_names = [item["name"] for item in exported_tables]

        dst = psycopg.connect(target_url, autocommit=True)
        replica_mode = False
        try:
            dst_tables = self._tables(dst)
            if source_table_names != dst_tables:
                only_src = sorted(set(source_table_names) - set(dst_tables))
                only_dst = sorted(set(dst_tables) - set(source_table_names))
                raise CommandError(
                    f"El esquema no coincide. Solo producción={only_src}; solo QA={only_dst}. "
                    "Se aborta antes de borrar datos."
                )

            for table_info in exported_tables:
                table = table_info["name"]
                if table_info["columns"] != self._columns(dst, table):
                    raise CommandError(
                        f"Las columnas no coinciden en {table}. Se aborta antes de borrar datos."
                    )

            try:
                dst.execute("SET session_replication_role = replica")
                replica_mode = True
            except Exception:
                pass

            ordered_tables = self._dependency_order(dst, dst_tables)
            table_info_by_name = {item["name"]: item for item in exported_tables}

            with dst.transaction():
                if not replica_mode:
                    try:
                        dst.execute("SET CONSTRAINTS ALL DEFERRED")
                    except Exception:
                        pass

                if dst_tables:
                    dst.execute(
                        sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                            sql.SQL(", ").join(sql.Identifier("public", t) for t in dst_tables)
                        )
                    )
                self.stdout.write(f"QA vaciada: {len(dst_tables)} tablas.")

                for table in ordered_tables:
                    table_info = table_info_by_name[table]
                    columns = table_info["columns"]
                    payload_file = bundle.extractfile(table_info["file"])
                    if payload_file is None:
                        raise CommandError(f"Falta el contenido de la tabla {table}.")
                    payload = payload_file.read()
                    if not columns:
                        continue
                    col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
                    copy_in = sql.SQL("COPY {} ({}) FROM STDIN").format(
                        sql.Identifier("public", table), col_sql
                    )
                    with dst.cursor().copy(copy_in) as inp:
                        inp.write(payload)

                for sequence_info in exported_sequences:
                    dst.execute(
                        "SELECT setval(%s::regclass, %s, %s)",
                        (
                            f'public."{sequence_info["name"]}"',
                            sequence_info["last_value"],
                            sequence_info["is_called"],
                        ),
                    )

            if replica_mode:
                dst.execute("SET session_replication_role = origin")
                replica_mode = False

            mismatches = []
            total_rows = 0
            for table_info in exported_tables:
                actual = self._count(dst, table_info["name"])
                expected = int(table_info["rows"])
                total_rows += actual
                if actual != expected:
                    mismatches.append((table_info["name"], expected, actual))

            if mismatches:
                raise CommandError(f"Hay diferencias de conteo luego de restaurar: {mismatches}")

            self.stdout.write(
                self.style.SUCCESS(
                    f"SYNC OK: {len(exported_tables)} tablas, {total_rows} filas verificadas "
                    f"y {len(exported_sequences)} secuencias restauradas."
                )
            )
        finally:
            if replica_mode:
                try:
                    dst.execute("SET session_replication_role = origin")
                except Exception:
                    pass
            dst.close()
            bundle.close()

    @staticmethod
    def _tables(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _columns(conn, table):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _count(conn, table):
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier("public", table)))
            return cur.fetchone()[0]

    @staticmethod
    def _dependency_order(conn, tables):
        deps = {table: set() for table in tables}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT child.relname, parent.relname
                FROM pg_constraint con
                JOIN pg_class child ON child.oid = con.conrelid
                JOIN pg_class parent ON parent.oid = con.confrelid
                JOIN pg_namespace n1 ON n1.oid = child.relnamespace
                JOIN pg_namespace n2 ON n2.oid = parent.relnamespace
                WHERE con.contype = 'f'
                  AND n1.nspname = 'public'
                  AND n2.nspname = 'public'
                """
            )
            for child, parent in cur.fetchall():
                if child in deps and parent in deps and child != parent:
                    deps[child].add(parent)

        ordered = []
        remaining = set(tables)
        while remaining:
            ready = sorted(table for table in remaining if not (deps[table] & remaining))
            if not ready:
                ready = sorted(remaining)
            for table in ready:
                ordered.append(table)
                remaining.remove(table)
        return ordered
