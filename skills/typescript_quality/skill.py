
import json
import re

from ...core.utils import text_files, files, result


def count_any_usages(content):
    pattern = r":\s*any\b|<any>|as\s+any\b"
    return len(re.findall(pattern, content))


def count_ts_ignores(content):
    return len(re.findall(r"@ts-ignore\b", content))


def remove_json_comments(content):
    """Remove // and /* */ comments without changing quoted strings."""
    output = []
    i = 0
    in_string = False
    escaped = False

    while i < len(content):
        char = content[i]
        next_char = content[i + 1] if i + 1 < len(content) else ""

        if in_string:
            output.append(char)

            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False

            i += 1
            continue

        if char == '"':
            in_string = True
            output.append(char)
            i += 1
        elif char == "/" and next_char == "/":
            i += 2
            while i < len(content) and content[i] not in "\r\n":
                i += 1
        elif char == "/" and next_char == "*":
            i += 2
            while i + 1 < len(content):
                if content[i:i + 2] == "*/":
                    i += 2
                    break
                i += 1
        else:
            output.append(char)
            i += 1

    return "".join(output)


def parse_tsconfig(path):
    """Read standard JSON and TypeScript JSONC configuration files."""
    try:
        content = path.read_text(encoding="utf-8")
        content = remove_json_comments(content)
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return None


def check_strict_mode(root):
    configs = [
        path for path in files(root)
        if path.name == "tsconfig.json"
    ]

    config_results = []

    for path in configs:
        data = parse_tsconfig(path)

        if data is None:
            config_results.append({
                "file": str(path.relative_to(root)),
                "strict": None,
                "message": "Could not parse configuration"
            })
            continue

        compiler_options = data.get("compilerOptions", {})
        strict = compiler_options.get("strict")

        if strict is True:
            message = "Strict mode enabled"
        elif strict is False:
            message = "Strict mode disabled"
        else:
            message = "Strict mode not explicitly configured"

        config_results.append({
            "file": str(path.relative_to(root)),
            "strict": strict,
            "message": message
        })

    if not config_results:
        return None, "No tsconfig.json files found", []

    strict_values = [
        item["strict"] for item in config_results
        if item["strict"] is not None
    ]

    if any(value is False for value in strict_values):
        overall = False
        message = "Strict mode is disabled in one or more configurations"
    elif not strict_values:
        overall = None
        message = "No configuration explicitly enables strict mode"
    elif any(item["strict"] is None for item in config_results):
        overall = None
        message = "Some TypeScript configurations could not be verified"
    else:
        overall = True
        message = "Strict mode enabled in all readable configurations"

    return overall, message, config_results


def find_unused_exports(root):
    source_files = [
        (path, content)
        for path, content in text_files(root)
        if path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}
    ]

    exported = {}

    for path, content in source_files:
        pattern = (
            r"\bexport\s+(?:const|let|var|function|class|"
            r"interface|type|enum)\s+(\w+)"
        )

        for match in re.finditer(pattern, content):
            name = match.group(1)
            exported.setdefault(name, []).append(path)

    unused = []

    for name, paths in exported.items():
        used_elsewhere = False

        for path, content in source_files:
            if path in paths:
                continue

            if re.search(r"\b" + re.escape(name) + r"\b", content):
                used_elsewhere = True
                break

        if not used_elsewhere:
            unused.append(name)

    return unused


def execute(root):
    ts_files = [
        (path, content)
        for path, content in text_files(root)
        if path.suffix.lower() in {".ts", ".tsx"}
    ]

    any_count = 0
    ignore_count = 0
    typed_declarations = 0
    total_declarations = 0

    for path, content in ts_files:
        any_count += count_any_usages(content)
        ignore_count += count_ts_ignores(content)

        declarations = re.findall(
            r"\b(?:const|let|var|function|class)\s+\w+",
            content
        )

        typed = re.findall(
            r"\b(?:const|let|var|function|class)\s+\w+\s*:\s*[\w<>\[\]|&?]+",
            content
        )

        total_declarations += len(declarations)
        typed_declarations += len(typed)

    strict_mode, strict_message, config_results = check_strict_mode(root)

    unused_exports = find_unused_exports(root)

    type_coverage = (
        round((typed_declarations / total_declarations) * 100, 2)
        if total_declarations else None
    )

    findings = []

    if not ts_files:
        findings.append({
            "severity": "WARN",
            "issue": "No TypeScript files found for quality inspection."
        })

    if any_count:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"Found {any_count} explicit any type usages."
        })

    if ignore_count:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"Found {ignore_count} @ts-ignore comments."
        })

    if strict_mode is False:
        findings.append({
            "severity": "HIGH",
            "issue": strict_message
        })

    if strict_mode is None:
        findings.append({
            "severity": "WARN",
            "issue": strict_message
        })

    if unused_exports:
        findings.append({
            "severity": "LOW",
            "issue": (
                f"Found {len(unused_exports)} potentially unused exports."
            )
        })

    if any_count or ignore_count or strict_mode is False:
        status = "WARN"
    elif not ts_files or strict_mode is None:
        status = "WARN"
    else:
        status = "PASS"

    summary = (
        f"Scanned {len(ts_files)} TypeScript files. "
        f"Found {any_count} any usages and "
        f"{ignore_count} @ts-ignore comments."
    )

    return result(
        "TypeScript Quality",
        status,
        summary,
        findings,
        {
            "typescript_files_scanned": len(ts_files),
            "any_usages": any_count,
            "ts_ignore_comments": ignore_count,
            "strict_mode": strict_mode,
            "strict_mode_message": strict_message,
            "typescript_configurations": config_results,
            "potentially_unused_exports": unused_exports,
            "estimated_type_coverage_percentage": type_coverage,
            "note": (
                "Unused export detection and type coverage are heuristic "
                "static estimates, not compiler-verified results."
            )
        }
    )
