"""Copy business data from SQL Server to MariaDB through PHP PDO, without disk dumps."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import pyodbc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHP_IMPORTER = Path(__file__).with_name("mariadb_pdo_import.php")
TABLE_ORDER = [
    "VaiTro",
    "ThietBi",
    "CaLamViec",
    "DanhMucBieuHien",
    "LoaiCanhBao",
    "NhanVien",
    "TaiKhoan",
    "LichSuSucKhoe",
    "ThongSoMoiTruong",
    "LichSuTrangThai",
    "PhanCaNhanVien",
    "ChamCong",
    "FaceEmbedding",
    "CanhBao",
]


def quote_sql_server_identifier(name: str) -> str:
    return "[" + name.replace("]", "]]" ) + "]"


def encode_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return {
            "__migration_type": "datetime",
            "value": value.isoformat(sep=" ", timespec="microseconds"),
        }
    if isinstance(value, date):
        return {"__migration_type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {
            "__migration_type": "time",
            "value": value.isoformat(timespec="microseconds"),
        }
    if isinstance(value, Decimal):
        return {"__migration_type": "decimal", "value": format(value, "f")}
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "__migration_type": "binary",
            "base64": base64.b64encode(raw).decode("ascii"),
        }
    raise TypeError(f"Unsupported SQL Server value type: {type(value).__name__}")


def send_message(stream, message) -> None:
    stream.write(json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    stream.write("\n")


def load_source_metadata(cursor):
    source_tables = {
        row[0]
        for row in cursor.execute(
            "SELECT t.name FROM sys.tables t "
            "WHERE t.schema_id = SCHEMA_ID('dbo') ORDER BY t.name"
        ).fetchall()
    }
    expected_source_tables = set(TABLE_ORDER) | {"sysdiagrams"}
    if source_tables != expected_source_tables:
        raise RuntimeError(
            "Unexpected SQL Server table set; refusing migration. "
            f"Expected 14 business tables and sysdiagrams, found {sorted(source_tables)}"
        )

    table_info = []
    for table_name in TABLE_ORDER:
        columns = cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            "dbo",
            table_name,
        ).fetchall()
        if not columns:
            raise RuntimeError(f"No source columns found for dbo.{table_name}.")

        primary_keys = cursor.execute(
            "SELECT c.name FROM sys.indexes i "
            "JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
            "JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
            "WHERE i.object_id = OBJECT_ID(?) AND i.is_primary_key = 1 "
            "ORDER BY ic.key_ordinal",
            f"dbo.{table_name}",
        ).fetchall()
        if len(primary_keys) != 1:
            raise RuntimeError(f"Expected one primary-key column in dbo.{table_name}.")

        column_names = [column[0] for column in columns]
        text_columns = [
            column[0]
            for column in columns
            if column[1].lower() in {"char", "varchar", "nchar", "nvarchar", "text", "ntext"}
        ]
        primary_key = primary_keys[0][0]
        binary_columns = [
            column[0]
            for column in columns
            if column[1].lower() in {"binary", "varbinary", "image"}
        ]
        aggregate_sql = ["COUNT_BIG(*)", f"MIN({quote_sql_server_identifier(primary_key)})", f"MAX({quote_sql_server_identifier(primary_key)})"]
        aggregate_sql.extend(
            "SUM(CASE WHEN " + quote_sql_server_identifier(column) +
            " IS NULL THEN CONVERT(bigint, 1) ELSE CONVERT(bigint, 0) END)"
            for column in column_names
        )
        aggregates = cursor.execute(
            f"SELECT {', '.join(aggregate_sql)} FROM dbo.{quote_sql_server_identifier(table_name)}"
        ).fetchone()
        null_counts = {
            column: int(aggregates[index + 3] or 0)
            for index, column in enumerate(column_names)
        }
        table_info.append(
            {
                "name": table_name,
                "columns": column_names,
                "text_columns": text_columns,
                "primary_key": primary_key,
                "binary_columns": binary_columns,
                "source_count": int(aggregates[0]),
                "source_min": None if aggregates[1] is None else int(aggregates[1]),
                "source_max": None if aggregates[2] is None else int(aggregates[2]),
                "null_counts": null_counts,
            }
        )

    foreign_key_rows = cursor.execute(
        "SELECT SCHEMA_NAME(parent.schema_id), parent.name, parent_column.name, "
        "SCHEMA_NAME(referenced.schema_id), referenced.name, referenced_column.name "
        "FROM sys.foreign_key_columns fkc "
        "JOIN sys.foreign_keys fk ON fk.object_id = fkc.constraint_object_id "
        "JOIN sys.tables parent ON parent.object_id = fkc.parent_object_id "
        "JOIN sys.columns parent_column ON parent_column.object_id = fkc.parent_object_id "
        "AND parent_column.column_id = fkc.parent_column_id "
        "JOIN sys.tables referenced ON referenced.object_id = fkc.referenced_object_id "
        "JOIN sys.columns referenced_column ON referenced_column.object_id = fkc.referenced_object_id "
        "AND referenced_column.column_id = fkc.referenced_column_id "
        "WHERE SCHEMA_NAME(parent.schema_id) = 'dbo' ORDER BY parent.name, fkc.constraint_column_id"
    ).fetchall()
    foreign_keys = [
        {
            "table": row[1],
            "column": row[2],
            "referenced_table": row[4],
            "referenced_column": row[5],
        }
        for row in foreign_key_rows
    ]
    if len(foreign_keys) != 16:
        raise RuntimeError(f"Expected 16 source foreign keys, found {len(foreign_keys)}.")

    rank = {name: index for index, name in enumerate(TABLE_ORDER)}
    for foreign_key in foreign_keys:
        if rank[foreign_key["referenced_table"]] >= rank[foreign_key["table"]]:
            raise RuntimeError(
                "Migration order violates a foreign key dependency: "
                f"{foreign_key['referenced_table']} must precede {foreign_key['table']}."
            )

    return table_info, foreign_keys


def run_migration() -> dict:
    if not PHP_IMPORTER.is_file():
        raise RuntimeError(f"PDO importer is missing: {PHP_IMPORTER}")

    php = os.environ.get("PHP_CLI", r"C:\xampp\php\php.exe")
    if not Path(php).is_file():
        raise RuntimeError(f"PHP CLI was not found: {php}")

    server = os.environ.get("SQLSERVER_HOST", "localhost")
    database = os.environ.get("SQLSERVER_DATABASE", "DoAn_ChamCong_AI")
    driver = os.environ.get("SQLSERVER_ODBC_DRIVER", "ODBC Driver 17 for SQL Server")
    connection_string = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        "Trusted_Connection=yes;ApplicationIntent=ReadOnly;"
    )

    source = pyodbc.connect(connection_string, timeout=10)
    process = None
    try:
        cursor = source.cursor()
        identity = cursor.execute("SELECT @@SERVERNAME, DB_NAME()").fetchone()
        if identity[1] != database:
            raise RuntimeError(f"Connected to unexpected SQL Server database: {identity[1]}")

        table_info, foreign_keys = load_source_metadata(cursor)
        process = subprocess.Popen(
            [php, str(PHP_IMPORTER)],
            cwd=PROJECT_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
        )

        send_message(process.stdin, {"type": "header", "tables": table_info, "foreign_keys": foreign_keys})
        process.stdin.flush()

        for table in table_info:
            names = ", ".join(quote_sql_server_identifier(column) for column in table["columns"])
            query = (
                f"SELECT {names} FROM dbo.{quote_sql_server_identifier(table['name'])} "
                f"ORDER BY {quote_sql_server_identifier(table['primary_key'])}"
            )
            cursor.execute(query)
            streamed = 0
            for row in cursor:
                encoded_values = []
                binary_checks = {}
                for index, value in enumerate(row):
                    encoded = encode_value(value)
                    column_name = table["columns"][index]
                    if isinstance(encoded, dict) and encoded.get("__migration_type") == "binary":
                        raw = bytes(value)
                        binary_checks[column_name] = {
                            "length": len(raw),
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        }
                    encoded_values.append(encoded)

                send_message(
                    process.stdin,
                    {"type": "row", "values": encoded_values, "binary_checks": binary_checks},
                )
                streamed += 1
                if streamed % 100 == 0:
                    process.stdin.flush()

            if streamed != table["source_count"]:
                raise RuntimeError(
                    f"Source row count changed while reading {table['name']}: "
                    f"expected {table['source_count']}, got {streamed}."
                )
            send_message(process.stdin, {"type": "table_end", "name": table["name"]})
            process.stdin.flush()

        process.stdin.close()
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        exit_code = process.wait()
        if exit_code != 0:
            raise RuntimeError(stderr.strip() or f"PHP PDO importer exited with status {exit_code}.")

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"PDO importer returned invalid verification output: {stdout[:500]!r}") from error
        if result.get("ok") is not True:
            raise RuntimeError("PDO importer did not report success.")
        return result
    except Exception:
        if process is not None and process.poll() is None:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            process.wait()
        raise
    finally:
        source.close()


def main() -> int:
    try:
        result = run_migration()
    except Exception as error:
        print(f"MIGRATION FAIL: {error}", file=sys.stderr)
        return 1

    print(f"MIGRATION PASS: {result['total_rows']} rows across {result['table_count']} tables.")
    print("SQL Server source: read-only SELECT via pyodbc; MariaDB destination: PHP PDO MySQL.")
    print("Per-table verification:")
    for table in result["tables"]:
        print(
            f"  {table['table']}: source={table['source_rows']}, destination={table['destination_rows']}, "
            f"PK={table['primary_key_min']}..{table['primary_key_max']}, "
            f"AUTO_INCREMENT={table['auto_increment_next']}"
        )

    embeddings = [row for row in result["binary_records"] if row["table"] == "FaceEmbedding"]
    evidence = [row for row in result["binary_records"] if row["table"] == "ChamCong"]
    print(f"FaceEmbedding: {len(embeddings)} binary rows, SHA-256/length/employee/dimensions verified.")
    for row in embeddings:
        print(
            f"  MaEmbedding={row['primary_key']} MaNV={row['employee_id']} SoChieu={row['dimensions']} "
            f"bytes={row['length']} sha256={row['sha256']}"
        )
    print(f"Attendance evidence: {len(evidence)} non-NULL binary values, SHA-256/length verified.")
    for row in evidence:
        print(f"  MaCC={row['primary_key']} {row['column']} bytes={row['length']} sha256={row['sha256']}")
    print(f"Foreign keys: {result['foreign_key_count']}/16 passed with zero orphans.")
    print(f"Unicode samples: {result['unicode_sample_count']} round-tripped exactly.")
    print("All rows, primary-key ranges, NULL counts, binary hashes, foreign keys and AUTO_INCREMENT checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
