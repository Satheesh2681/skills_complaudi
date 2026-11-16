
import re
from pathlib import Path

from ...core.utils import result, text_files


def execute(root):
    findings = []
    migration_files = []
    source_files = []
    rls_enabled = 0
    raw_sql_count = 0
    index_count = 0

    migration_pattern = re.compile(
        r"(migrations?|prisma|supabase)",
        re.IGNORECASE,
    )

    raw_sql_pattern = re.compile(
        r"\b(?:SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
        re.IGNORECASE,
    )

    index_pattern = re.compile(
        r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b",
        re.IGNORECASE,
    )

    rls_pattern = re.compile(
        r"ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        re.IGNORECASE,
    )

    for path, content in text_files(root):
        relative = path.relative_to(root)
        suffix = path.suffix.lower()

        if migration_pattern.search(str(relative)):
            migration_files.append(str(relative))

        if suffix in {".js", ".jsx", ".ts", ".tsx", ".sql", ".py"}:
            source_files.append((path, content))

        rls_enabled += len(rls_pattern.findall(content))
        index_count += len(index_pattern.findall(content))

        if suffix in {".js", ".jsx", ".ts", ".tsx", ".py"}:
            raw_sql_count += len(raw_sql_pattern.findall(content))

    if not migration_files:
        findings.append({
            "severity": "MEDIUM",
            "message": "No database migration files detected.",
            "recommendation": "Check whether database schema changes are tracked through migrations.",
        })

    if rls_enabled == 0:
        findings.append({
            "severity": "HIGH",
            "message": "No Row Level Security enablement statements detected.",
            "recommendation": "Review database tables and enable RLS where appropriate.",
        })

    if raw_sql_count:
        findings.append({
            "severity": "MEDIUM",
            "message": f"Found {raw_sql_count} possible raw SQL statements in application source.",
            "recommendation": "Review SQL statements for parameterization and injection risks.",
        })

    if index_count == 0:
        findings.append({
            "severity": "LOW",
            "message": "No SQL index creation statements detected.",
            "recommendation": "Review frequently queried columns and migration index coverage.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {len(source_files)} application source files. "
        f"Found {len(migration_files)} migration-related files, "
        f"{rls_enabled} RLS enablement statements, "
        f"{raw_sql_count} possible raw SQL statements, "
        f"and {index_count} index creation statements."
    )

    return result(
        "Database Safety",
        status,
        summary,
        findings,
        {
            "source_files_scanned": len(source_files),
            "migration_files": migration_files[:100],
            "rls_enablement_count": rls_enabled,
            "possible_raw_sql_count": raw_sql_count,
            "index_creation_count": index_count,
            "analysis_type": "Heuristic static analysis",
        },
    )
