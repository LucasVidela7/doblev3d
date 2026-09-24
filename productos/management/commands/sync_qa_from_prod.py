import os

import psycopg
from django.core.management.base import BaseCommand, CommandError
from psycopg import sql


class Command(BaseCommand):
    help = "Clona los datos de PostgreSQL de production hacia QA. Solo puede ejecutarse en QA."

    def handle(self, *args, **options):
        env = (os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("APP_ENV") or "").strip().lower()
        if env != "qa":
            raise CommandError(f"Este comando solo puede ejecutarse en QA. Entorno detectado: {env!r}")

        source_url = os.getenv("DB_SYNC_SOURCE_URL")
        target_url = os.getenv("DATABASE_URL")
        if not source_url or not target_url:
            raise CommandError("Faltan DB_SYNC_SOURCE_URL o DATABASE_URL.")

        src = psycopg.connect(source_url, autocommit=False)
        dst = psycopg.connect(target_url, autocommit=True)

        try:
            src_id = self._db_identity(src)
            dst_id = self._db_identity(dst)
            self.stdout.write(f"Origen: {src_id}")
            self.stdout.write(f"Destino: {dst_id}")
            if src_id == dst_id:
                raise CommandError("Origen y destino resuelven a la misma base. Se aborta antes de borrar datos.")

            src_tables = self._tables(src)
            dst_tables = self._tables(dst)
            if src_tables != dst_tables:
                only_src = sorted(set(src_tables) - set(dst_tables))
                only_dst = sorted(set(dst_tables) - set(src_tables))
                raise CommandError(
                    f"El esquema no coincide. Solo origen={only_src}; solo destino={only_dst}"
                )

            for table in src_tables:
                if self._columns(src, table) != self._columns(dst, table):
                    raise CommandError(f"Las columnas no coinciden en la tabla {table}.")

            src.execute("BEGIN")
            src.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

            replica_mode = False
            try:
                dst.execute("SET session_replication_role = replica")
                replica_mode = True
            except Exception:
                pass

            ordered_tables = self._dependency_order(dst, dst_tables)

            with dst.transaction():
                if not replica_mode:
                    try:
                        dst.execute("SET CONSTRAINTS ALL DEFERRED")
                    except Exception:
                        pass

                if dst_tables:
                    truncate_sql = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                        sql.SQL(", ").join(sql.Identifier("public", t) for t in dst_tables)
                    )
                    dst.execute(truncate_sql)
                self.stdout.write(f"QA vaciada: {len(dst_tables)} tablas.")

                for table in ordered_tables:
                    columns = self._columns(src, table)
                    if not columns:
                        continue
                    col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
                    copy_out = sql.SQL("COPY {} ({}) TO STDOUT").format(
                        sql.Identifier("public", table), col_sql
                    )
                    copy_in = sql.SQL("COPY {} ({}) FROM STDIN").format(
                        sql.Identifier("public", table), col_sql
                    )
                    with src.cursor().copy(copy_out) as out, dst.cursor().copy(copy_in) as inp:
                        for chunk in out:
                            inp.write(chunk)

                for sequence in self._sequences(src):
                    with src.cursor() as cur:
                        cur.execute(
                            sql.SQL("SELECT last_value, is_called FROM {}").format(
                                sql.Identifier("public", sequence)
                            )
                        )
                        last_value, is_called = cur.fetchone()
                    dst.execute(
                        "SELECT setval(%s::regclass, %s, %s)",
                        (f'public."{sequence}"', last_value, is_called),
                    )

            if replica_mode:
                dst.execute("SET session_replication_role = origin")

            mismatches = []
            total_rows = 0
            for table in dst_tables:
                source_count = self._count(src, table)
                target_count = self._count(dst, table)
                total_rows += target_count
                if source_count != target_count:
                    mismatches.append((table, source_count, target_count))

            if mismatches:
                raise CommandError(f"Hay diferencias de conteo luego de restaurar: {mismatches}")

            self.stdout.write(
                self.style.SUCCESS(
                    f"SYNC OK: {len(dst_tables)} tablas, {total_rows} filas verificadas y secuencias restauradas."
                )
            )
        finally:
            try:
                src.rollback()
            except Exception:
                pass
            src.close()
            dst.close()

    @staticmethod
    def _db_identity(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr()::text, inet_server_port()")
            return cur.fetchone()

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
    def _sequences(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'S' AND n.nspname = 'public'
                ORDER BY c.relname
                """
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
