import io
import json
import os
import secrets
import tarfile

import psycopg
from django.http import HttpResponse, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
from psycopg import sql


def _authorized(request):
    expected = os.getenv("DB_SYNC_TOKEN", "")
    auth = request.headers.get("Authorization", "")
    if not expected or not auth.startswith("Bearer "):
        return False
    supplied = auth[7:]
    return secrets.compare_digest(expected, supplied)


@csrf_exempt
def db_sync_export(request):
    env = (os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("APP_ENV") or "").strip().lower()
    if request.method != "POST" or env != "production" or not _authorized(request):
        return HttpResponseNotFound()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return HttpResponse("DATABASE_URL missing", status=500)

    conn = psycopg.connect(database_url, autocommit=False)
    try:
        conn.execute("BEGIN")
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            tables = [row[0] for row in cur.fetchall()]

        metadata = {"tables": [], "sequences": []}
        bundle = io.BytesIO()

        with tarfile.open(fileobj=bundle, mode="w:gz") as tar:
            for index, table in enumerate(tables):
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
                    columns = [row[0] for row in cur.fetchall()]
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier("public", table))
                    )
                    row_count = cur.fetchone()[0]

                col_sql = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
                copy_query = sql.SQL("COPY {} ({}) TO STDOUT").format(
                    sql.Identifier("public", table), col_sql
                )
                table_bytes = io.BytesIO()
                with conn.cursor().copy(copy_query) as copy:
                    for chunk in copy:
                        table_bytes.write(bytes(chunk))
                payload = table_bytes.getvalue()

                filename = f"tables/{index:04d}.copy"
                info = tarfile.TarInfo(filename)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
                metadata["tables"].append(
                    {
                        "name": table,
                        "columns": columns,
                        "rows": row_count,
                        "file": filename,
                    }
                )

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
                sequences = [row[0] for row in cur.fetchall()]

            for sequence in sequences:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("SELECT last_value, is_called FROM {}").format(
                            sql.Identifier("public", sequence)
                        )
                    )
                    last_value, is_called = cur.fetchone()
                metadata["sequences"].append(
                    {
                        "name": sequence,
                        "last_value": last_value,
                        "is_called": is_called,
                    }
                )

            metadata_payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
            info = tarfile.TarInfo("metadata.json")
            info.size = len(metadata_payload)
            tar.addfile(info, io.BytesIO(metadata_payload))

        conn.rollback()
        response = HttpResponse(bundle.getvalue(), content_type="application/gzip")
        response["Cache-Control"] = "no-store"
        response["Content-Disposition"] = 'attachment; filename="db-sync-prod.tar.gz"'
        response["X-DB-Sync-Tables"] = str(len(tables))
        return response
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
