
import re
from pathlib import Path

from ...core.utils import result, text_files


def execute(root):
    findings = []
    readme = root / "README.md"
    readme_content = ""

    if readme.exists():
        readme_content = readme.read_text(encoding="utf-8", errors="ignore")
    else:
        findings.append({
            "severity": "HIGH",
            "message": "README.md is missing.",
            "recommendation": "Add a README with project setup, usage, and deployment instructions.",
        })

    sections = {
        "setup": r"installation|getting started|setup|prerequisites",
        "usage": r"usage|how to use|examples|quick start",
        "deployment": r"deployment|deploy|production",
    }

    section_results = {
        name: bool(re.search(pattern, readme_content, re.IGNORECASE))
        for name, pattern in sections.items()
    }

    for name, found in section_results.items():
        if not found and readme.exists():
            findings.append({
                "severity": "MEDIUM",
                "message": f"README may be missing a {name} section.",
                "recommendation": f"Add clear {name} documentation to README.md.",
            })

    api_docs = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
        and path.name.lower() in {
            "openapi.yaml", "openapi.yml", "swagger.yaml",
            "swagger.yml", "openapi.json"
        }
        and not any(
            part in {"node_modules", ".git", "dist", "build"}
            for part in path.relative_to(root).parts
        )
    ]

    source_extensions = {".js", ".jsx", ".ts", ".tsx", ".py"}
    exported_functions = 0
    documented_exports = 0

    export_pattern = re.compile(
        r"^\s*export\s+(?:async\s+)?function\s+[\w$]+|"
        r"^\s*export\s+(?:const|let|var)\s+[\w$]+\s*=",
        re.MULTILINE,
    )

    for path, content in text_files(root):
        if path.suffix.lower() not in source_extensions:
            continue

        matches = list(export_pattern.finditer(content))
        exported_functions += len(matches)

        for match in matches:
            before = content[:match.start()].rstrip()
            if re.search(r"/\*\*[\s\S]*?\*/\s*$", before):
                documented_exports += 1

    if not api_docs:
        findings.append({
            "severity": "LOW",
            "message": "No OpenAPI or Swagger specification file detected.",
            "recommendation": "Consider documenting available APIs with OpenAPI or Swagger.",
        })

    undocumented = exported_functions - documented_exports

    if undocumented > 0:
        findings.append({
            "severity": "LOW",
            "message": f"{undocumented} exported functions may lack JSDoc comments.",
            "recommendation": "Add JSDoc documentation to important exported functions.",
        })

    status = "WARN" if findings else "PASS"

    summary = (
        f"README present: {readme.exists()}. "
        f"Documented sections: {sum(section_results.values())}/3. "
        f"API specification files: {len(api_docs)}. "
        f"Exported functions: {exported_functions}; "
        f"with nearby JSDoc comments: {documented_exports}."
    )

    return result(
        "Documentation",
        status,
        summary,
        findings,
        {
            "readme_exists": readme.exists(),
            "readme_sections": section_results,
            "api_documentation_files": api_docs[:100],
            "exported_functions": exported_functions,
            "documented_exports": documented_exports,
            "analysis_type": "Heuristic static analysis",
        },
    )
