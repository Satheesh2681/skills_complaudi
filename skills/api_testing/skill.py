
import os
import re
from pathlib import Path

from ...core.utils import result


SKIP_DIRECTORIES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
}

HTTP_METHOD_PATTERN = re.compile(
    r"\b(?:[A-Za-z_$][\w$]*Router|router|app)\s*\.\s*"
    r"(get|post|put|patch|delete|options|head|all)\s*\(",
    re.IGNORECASE,
)

AUTH_PATTERN = re.compile(
    r"\b(?:requireAuth|requireCapability|authenticate|"
    r"authMiddleware|verifyToken|verifyJWT|isAuthenticated|"
    r"passport\.authenticate|JOB_TRIGGER_SECRET|"
    r"timingSafeEqual)\b",
    re.IGNORECASE,
)

SCHEMA_PATTERN = re.compile(
    r"\b(?:validateBody|validateParams|validateQuery|"
    r"validateRequest|z\.object|safeParse|"
    r"Joi|celebrate|Yup|yup|checkSchema|"
    r"express-validator|Ajv)\b",
    re.IGNORECASE,
)

ERROR_PATTERN = re.compile(
    r"\b(?:asyncHandler|try\s*\{|catch\s*\(|"
    r"next\s*\(|errorHandler|handleError)\b",
    re.IGNORECASE,
)


def read_file(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def find_route_files(root):
    """Find only actual backend module route files."""
    modules_dir = root / "src" / "modules"

    if not modules_dir.is_dir():
        return []

    route_files = []

    for current, directories, filenames in os.walk(modules_dir):
        directories[:] = [
            directory
            for directory in directories
            if directory not in SKIP_DIRECTORIES
        ]

        for filename in filenames:
            if filename.endswith((".routes.ts", ".routes.js")):
                route_files.append(Path(current) / filename)

    return sorted(route_files)


def count_route_declarations(content):
    """Count Express HTTP route declarations."""
    matches = list(HTTP_METHOD_PATTERN.finditer(content))
    routes = []

    for match in matches:
        method = match.group(1).upper()

        # Extract the route declaration arguments while respecting
        # nested parentheses in middleware and handler functions.
        opening = match.end() - 1
        depth = 0
        quote = None
        escaped = False
        closing = None

        for index in range(opening, len(content)):
            char = content[index]

            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue

            if char in ("'", '"', "`"):
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1

                if depth == 0:
                    closing = index
                    break

        if closing is None:
            continue

        arguments = content[opening + 1:closing]

        routes.append({
            "method": method,
            "arguments": arguments,
            "authentication_signal": bool(
                AUTH_PATTERN.search(arguments)
            ),
            "schema_validation_signal": bool(
                SCHEMA_PATTERN.search(arguments)
            ),
            "error_handling_signal": bool(
                ERROR_PATTERN.search(arguments)
            ),
        })

    return routes


def inspect_app_configuration(root):
    """Inspect app.ts for route mounting and global error handling."""
    app_file = root / "src" / "app.ts"
    content = read_file(app_file)

    if content is None:
        return {
            "available": False,
            "central_error_handler": False,
            "public_route_files": [],
            "mounted_route_files": [],
        }

    central_error_handler = bool(
        re.search(
            r"\bapp\s*\.\s*use\s*\(\s*errorHandler\s*\)",
            content,
        )
    )

    mounted_route_files = re.findall(
        r"\bapp\s*\.\s*use\s*\([^,]+,\s*(\w+Router)\s*\)",
        content,
    )

    public_route_files = []

    # The contact router is explicitly mounted outside the
    # authenticated API router in the supplied app.ts.
    if re.search(
        r"\bapp\s*\.\s*use\s*\(\s*"
        r"['\"]\/api\/v1\/contact['\"]\s*,\s*contactRouter",
        content,
    ):
        public_route_files.append("contact.routes.ts")

    return {
        "available": True,
        "central_error_handler": central_error_handler,
        "public_route_files": public_route_files,
        "mounted_route_files": mounted_route_files,
    }


def analyze_route_file(path, root, app_config):
    content = read_file(path)

    if content is None:
        return None

    relative_path = str(path.relative_to(root))
    routes = count_route_declarations(content)

    file_auth_signal = bool(AUTH_PATTERN.search(content))
    file_schema_signal = bool(SCHEMA_PATTERN.search(content))
    file_error_signal = bool(ERROR_PATTERN.search(content))

    public_route = path.name in app_config["public_route_files"]

    protected_routes = sum(
        route["authentication_signal"] for route in routes
    )

    validated_routes = sum(
        route["schema_validation_signal"] for route in routes
    )

    route_error_signals = sum(
        route["error_handling_signal"] for route in routes
    )

    findings = []

    # Do not flag explicitly public routes such as the contact form.
    if (
        routes
        and not file_auth_signal
        and not public_route
    ):
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No recognizable authentication or access-control "
                "signal found. Verify whether this router is "
                "intentionally public or protected elsewhere."
            ),
            "file": relative_path,
        })

    if routes and not file_schema_signal:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No recognizable request-schema validation signal "
                "found in this route file."
            ),
            "file": relative_path,
        })

    # asyncHandler and try/catch are local error-handling signals.
    # A centralized handler alone does not prove async errors are forwarded.
    if routes and not file_error_signal:
        findings.append({
            "severity": "REVIEW",
            "issue": (
                "No recognizable local error-handling signal found."
            ),
            "file": relative_path,
        })

    return {
        "file": relative_path,
        "route_count": len(routes),
        "methods": [
            route["method"] for route in routes
        ],
        "authentication_signal": file_auth_signal,
        "protected_route_count": protected_routes,
        "schema_validation_signal": file_schema_signal,
        "validated_route_count": validated_routes,
        "error_handling_signal": file_error_signal,
        "route_error_signal_count": route_error_signals,
        "public_route": public_route,
        "findings": findings,
    }


def execute(root):
    root = Path(root).resolve()

    app_config = inspect_app_configuration(root)
    route_files = find_route_files(root)

    if not route_files:
        return result(
            "API Testing",
            "WARN",
            "No backend module route files were found.",
            [{
                "severity": "REVIEW",
                "issue": (
                    "Expected route files under src/modules "
                    "with .routes.ts or .routes.js extensions."
                ),
            }],
            {
                "route_files_scanned": 0,
                "app_configuration": app_config,
            },
        )

    route_details = []
    unreadable_files = []

    for path in route_files:
        details = analyze_route_file(path, root, app_config)

        if details is None:
            unreadable_files.append(str(path.relative_to(root)))
            continue

        route_details.append(details)

    total_routes = sum(
        item["route_count"] for item in route_details
    )

    auth_files = sum(
        item["authentication_signal"] for item in route_details
    )

    schema_files = sum(
        item["schema_validation_signal"] for item in route_details
    )

    error_files = sum(
        item["error_handling_signal"] for item in route_details
    )

    findings = []

    for item in route_details:
        findings.extend(item["findings"])

    status = "WARN" if findings or unreadable_files else "PASS"

    summary = (
        f"Scanned {len(route_details)} backend route files "
        f"and detected {total_routes} HTTP route declarations. "
        f"Found {len(findings)} items requiring review."
    )

    return result(
        "API Testing",
        status,
        summary,
        findings,
        {
            "route_files_scanned": len(route_details),
            "total_route_definitions": total_routes,
            "files_with_authentication_signals": auth_files,
            "files_with_schema_validation_signals": schema_files,
            "files_with_error_handling_signals": error_files,
            "central_error_handler_registered": (
                app_config["central_error_handler"]
            ),
            "app_configuration_available": app_config["available"],
            "public_route_files": app_config["public_route_files"],
            "route_file_details": route_details,
            "unreadable_files": unreadable_files,
            "note": (
                "This is heuristic static analysis, not live API testing. "
                "Authentication and validation may be applied through "
                "imported or externally registered middleware. Public "
                "routes are not automatically vulnerabilities. "
                "A missing signal requires manual verification and "
                "does not prove a security issue. No HTTP requests "
                "or application data modifications are performed."
            ),
        },
    )
