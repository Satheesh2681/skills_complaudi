
import json
import re
from collections import Counter
from pathlib import Path
from html import unescape
from ...core.utils import result, text_files


SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv",
    "dist", "build", "coverage", ".next",
    "playwright-report", "test-results", "__pycache__"
}


def attributes(tag):
    found = {}
    pattern = r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""

    for match in re.finditer(pattern, tag):
        value = next(
            (group for group in match.groups()[1:] if group is not None),
            ""
        )
        found[match.group(1).lower()] = unescape(value.strip())

    return found


def execute(root):
    root = Path(root)
    findings = []
    html_pages = []
    details = {
        "analysis_type": "Static SEO inspection",
        "html_files_scanned": 0,
        "metadata": {},
        "images": {},
        "headings": {},
        "links": {},
        "social_metadata": {},
        "structured_data": {},
        "crawlability": {},
        "url_quality": {},
        "https_signals": {},
    }

    title_values = []
    description_values = []
    canonical_values = []
    all_images = 0
    missing_alt = 0
    empty_alt = 0
    pages_without_h1 = 0
    pages_with_multiple_h1 = 0
    empty_links = 0
    placeholder_links = 0
    internal_links = 0
    external_links = 0
    http_links = 0
    og_pages = 0
    twitter_pages = 0
    jsonld_blocks = 0
    schema_pages = 0
    noindex_pages = 0
    nofollow_pages = 0
    missing_viewport = 0
    missing_language = 0
    long_urls = []
    uppercase_urls = []
    heading_jumps = []
    invalid_jsonld = []

    html_pattern = re.compile(r"\.html?$", re.IGNORECASE)

    for path, content in text_files(root):
        if not html_pattern.search(path.name):
            continue

        relative = path.relative_to(root).as_posix()
        html_pages.append(relative)
        lower = content.lower()

        # Title
        title_match = re.search(
            r"<title\b[^>]*>(.*?)</title\s*>",
            content,
            re.IGNORECASE | re.DOTALL
        )
        title = re.sub(r"\s+", " ", unescape(title_match.group(1))).strip() if title_match else ""

        if not title:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Missing or empty title tag."
            })
        else:
            title_values.append((title.lower(), relative))
            if len(title) > 60:
                findings.append({
                    "severity": "LOW",
                    "file": relative,
                    "issue": f"Title is longer than 60 characters ({len(title)})."
                })

        # Meta tags
        meta_tags = [
            attributes(tag)
            for tag in re.findall(r"<meta\b[^>]*>", content, re.IGNORECASE)
        ]

        descriptions = [
            item.get("content", "").strip()
            for item in meta_tags
            if item.get("name", "").lower() == "description"
        ]
        description = next((value for value in descriptions if value), "")

        if not description:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Missing or empty meta description."
            })
        else:
            description_values.append((description.lower(), relative))
            if len(description) > 160:
                findings.append({
                    "severity": "LOW",
                    "file": relative,
                    "issue": f"Meta description is longer than 160 characters ({len(description)})."
                })

        if len(descriptions) > 1:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Multiple meta description tags detected."
            })

        viewport = any(
            item.get("name", "").lower() == "viewport"
            for item in meta_tags
        )
        if not viewport:
            missing_viewport += 1
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Missing viewport metadata."
            })

        robots_values = [
            item.get("content", "").lower()
            for item in meta_tags
            if item.get("name", "").lower() == "robots"
        ]

        if any("noindex" in value for value in robots_values):
            noindex_pages += 1

        if any("nofollow" in value for value in robots_values):
            nofollow_pages += 1

        # Canonical URL
        canonical_tags = [
            attributes(tag)
            for tag in re.findall(r"<link\b[^>]*>", content, re.IGNORECASE)
            if attributes(tag).get("rel", "").lower() == "canonical"
        ]

        canonical = next(
            (item.get("href", "").strip() for item in canonical_tags
             if item.get("href", "").strip()),
            ""
        )

        if not canonical:
            findings.append({
                "severity": "LOW",
                "file": relative,
                "issue": "Canonical URL not detected."
            })
        else:
            canonical_values.append((canonical.lower(), relative))

        if len(canonical_tags) > 1:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Multiple canonical link tags detected."
            })

        # Language
        html_tag = re.search(r"<html\b[^>]*>", content, re.IGNORECASE)
        html_attrs = attributes(html_tag.group(0)) if html_tag else {}

        if not html_attrs.get("lang"):
            missing_language += 1
            findings.append({
                "severity": "LOW",
                "file": relative,
                "issue": "HTML lang attribute is missing."
            })

        # Images and ALT attributes
        images = re.findall(r"<img\b[^>]*>", content, re.IGNORECASE)
        all_images += len(images)

        for image_tag in images:
            image_attrs = attributes(image_tag)

            if "alt" not in image_attrs:
                missing_alt += 1
            elif not image_attrs["alt"].strip():
                empty_alt += 1

        # Headings
        headings = [
            int(level)
            for level in re.findall(
                r"<h([1-6])\b",
                content,
                re.IGNORECASE
            )
        ]

        h1_count = headings.count(1)

        if h1_count == 0:
            pages_without_h1 += 1
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "No H1 heading detected."
            })

        if h1_count > 1:
            pages_with_multiple_h1 += 1
            findings.append({
                "severity": "LOW",
                "file": relative,
                "issue": f"Multiple H1 headings detected ({h1_count})."
            })

        previous = 0
        for level in headings:
            if previous and level > previous + 1:
                heading_jumps.append(relative)
                findings.append({
                    "severity": "LOW",
                    "file": relative,
                    "issue": f"Heading hierarchy jumps from H{previous} to H{level}."
                })
                break
            previous = level

        # Links
        anchors = re.findall(r"<a\b[^>]*>", content, re.IGNORECASE)

        for anchor in anchors:
            href = attributes(anchor).get("href", "").strip()

            if not href:
                empty_links += 1
                continue

            if href == "#":
                placeholder_links += 1

            if href.lower().startswith("http://"):
                http_links += 1

            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            if href.startswith("https://"):
                external_links += 1
            elif href.startswith("//"):
                external_links += 1
            else:
                internal_links += 1

        # Open Graph and Twitter metadata
        has_og = any(
            item.get("property", "").lower().startswith("og:")
            for item in meta_tags
        )
        has_twitter = any(
            item.get("name", "").lower().startswith("twitter:")
            for item in meta_tags
        )

        if has_og:
            og_pages += 1
        else:
            findings.append({
                "severity": "LOW",
                "file": relative,
                "issue": "Open Graph metadata not detected."
            })

        if has_twitter:
            twitter_pages += 1
        else:
            findings.append({
                "severity": "LOW",
                "file": relative,
                "issue": "Twitter Card metadata not detected."
            })

        # Structured data
        scripts = re.findall(
            r"<script\b([^>]*)>(.*?)</script\s*>",
            content,
            re.IGNORECASE | re.DOTALL
        )

        for script_attrs, script_content in scripts:
            attrs = attributes(script_attrs)

            if attrs.get("type", "").lower() != "application/ld+json":
                continue

            jsonld_blocks += 1

            try:
                data = json.loads(script_content.strip())

                serialized = json.dumps(data).lower()
                if "schema.org" in serialized:
                    schema_pages += 1

            except (json.JSONDecodeError, TypeError):
                invalid_jsonld.append(relative)
                findings.append({
                    "severity": "MEDIUM",
                    "file": relative,
                    "issue": "Invalid JSON-LD structured data."
                })

        # URL quality
        if len(relative) > 100:
            long_urls.append(relative)

        if any(char.isupper() for char in relative):
            uppercase_urls.append(relative)

    details["html_files_scanned"] = len(html_pages)

    if not html_pages:
        findings.append({
            "severity": "WARN",
            "issue": "No HTML files found for SEO inspection."
        })

    # Duplicate titles
    title_counts = Counter(value for value, _ in title_values)
    for value, relative in title_values:
        if title_counts[value] > 1:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Duplicate page title detected."
            })

    # Duplicate descriptions
    description_counts = Counter(value for value, _ in description_values)
    for value, relative in description_values:
        if description_counts[value] > 1:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Duplicate meta description detected."
            })

    # Duplicate canonical URLs
    canonical_counts = Counter(value for value, _ in canonical_values)
    for value, relative in canonical_values:
        if canonical_counts[value] > 1:
            findings.append({
                "severity": "MEDIUM",
                "file": relative,
                "issue": "Canonical URL is repeated across multiple HTML files."
            })

    # Image findings
    if missing_alt:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"{missing_alt} images are missing ALT attributes."
        })

    if empty_alt:
        findings.append({
            "severity": "INFO",
            "issue": f"{empty_alt} images have empty ALT text; verify whether they are decorative."
        })

    # Link findings
    if empty_links:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"{empty_links} anchor elements have no href attribute or an empty href."
        })

    if placeholder_links:
        findings.append({
            "severity": "LOW",
            "issue": f"{placeholder_links} links use href='#'."
        })

    if http_links:
        findings.append({
            "severity": "MEDIUM",
            "issue": f"{http_links} links use insecure HTTP URLs."
        })

    # Crawlability files
    def find_named_files(filename):
        matches = []
        for path in root.rglob(filename):
            if not any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                matches.append(path.relative_to(root).as_posix())
        return matches

    robots_files = find_named_files("robots.txt")
    sitemap_files = find_named_files("sitemap.xml")

    if not robots_files:
        findings.append({
            "severity": "LOW",
            "issue": "robots.txt not found."
        })

    if not sitemap_files:
        findings.append({
            "severity": "LOW",
            "issue": "sitemap.xml not found."
        })

    if noindex_pages:
        findings.append({
            "severity": "INFO",
            "issue": f"{noindex_pages} pages contain a noindex directive; verify that this is intentional."
        })

    # URL quality
    for relative in long_urls:
        findings.append({
            "severity": "LOW",
            "file": relative,
            "issue": "Long page path detected."
        })

    for relative in uppercase_urls:
        findings.append({
            "severity": "LOW",
            "file": relative,
            "issue": "Uppercase characters found in page path."
        })

    details["metadata"] = {
        "titles_found": len(title_values),
        "descriptions_found": len(description_values),
        "canonical_urls_found": len(canonical_values),
        "pages_missing_viewport": missing_viewport,
        "pages_missing_language": missing_language,
    }

    details["images"] = {
        "total_images": all_images,
        "missing_alt": missing_alt,
        "empty_alt": empty_alt,
    }

    details["headings"] = {
        "pages_without_h1": pages_without_h1,
        "pages_with_multiple_h1": pages_with_multiple_h1,
        "heading_hierarchy_issues": len(heading_jumps),
    }

    details["links"] = {
        "internal_link_signals": internal_links,
        "external_link_signals": external_links,
        "empty_links": empty_links,
        "placeholder_links": placeholder_links,
        "http_links": http_links,
        "broken_links_checked": False,
    }

    details["social_metadata"] = {
        "pages_with_open_graph": og_pages,
        "pages_with_twitter_cards": twitter_pages,
    }

    details["structured_data"] = {
        "json_ld_blocks": jsonld_blocks,
        "pages_with_schema_org_signals": schema_pages,
        "invalid_jsonld_files": invalid_jsonld[:100],
    }

    details["crawlability"] = {
        "robots_files": robots_files,
        "sitemap_files": sitemap_files,
        "pages_with_noindex": noindex_pages,
        "pages_with_nofollow": nofollow_pages,
    }

    details["url_quality"] = {
        "long_page_paths": long_urls[:100],
        "uppercase_page_paths": uppercase_urls[:100],
    }

    details["https_signals"] = {
        "http_links_detected": http_links,
        "site_https_verified": False,
    }

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {len(html_pages)} HTML files; "
        f"found {len(findings)} SEO findings, "
        f"{missing_alt} images missing ALT attributes, "
        f"{pages_without_h1} pages without H1, "
        f"{jsonld_blocks} JSON-LD blocks, and "
        f"{http_links} HTTP links. "
        "External link availability and actual search indexing were not tested."
    )

    return result(
        "SEO",
        status,
        summary,
        findings[:500],
        details
    )
