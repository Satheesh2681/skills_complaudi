
from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from ...core.utils import result, text_files


VALID_ROLES = {
    "alert", "alertdialog", "application", "article", "banner",
    "button", "cell", "checkbox", "columnheader", "combobox",
    "complementary", "contentinfo", "definition", "dialog",
    "directory", "document", "feed", "figure", "form", "grid",
    "gridcell", "group", "heading", "img", "link", "list",
    "listbox", "listitem", "log", "main", "marquee", "math",
    "menu", "menubar", "menuitem", "menuitemcheckbox",
    "menuitemradio", "meter", "navigation", "none", "note",
    "option", "presentation", "progressbar", "radio",
    "radiogroup", "region", "row", "rowgroup", "rowheader",
    "scrollbar", "search", "searchbox", "separator", "slider",
    "spinbutton", "status", "switch", "tab", "table",
    "tablist", "tabpanel", "term", "textbox", "timer",
    "toolbar", "tooltip", "tree", "treegrid", "treeitem"
}

INTERACTIVE = {"button", "input", "select", "textarea"}
FORM_CONTROLS = {"input", "select", "textarea"}

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr"
}

COLOR_NAMES = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
}


def parse_color(value):
    """Parse common CSS hex, named, and RGB colors."""
    if not value:
        return None

    value = value.strip().lower()

    if value in COLOR_NAMES:
        return COLOR_NAMES[value]

    if value.startswith("#"):
        code = value[1:]

        if len(code) == 3:
            code = "".join(char * 2 for char in code)

        if len(code) == 6:
            try:
                return tuple(
                    int(code[index:index + 2], 16)
                    for index in (0, 2, 4)
                )
            except ValueError:
                return None

    match = re.fullmatch(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,"
        r"\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)",
        value
    )

    if match:
        channels = tuple(int(value) for value in match.groups())

        if all(0 <= channel <= 255 for channel in channels):
            return channels

    return None


def contrast_ratio(foreground, background):
    """Calculate the WCAG contrast ratio between two RGB colors."""

    def luminance(color):
        values = []

        for channel in color:
            channel = channel / 255

            if channel <= 0.04045:
                values.append(channel / 12.92)
            else:
                values.append(
                    ((channel + 0.055) / 1.055) ** 2.4
                )

        return (
            0.2126 * values[0]
            + 0.7152 * values[1]
            + 0.0722 * values[2]
        )

    first = luminance(foreground)
    second = luminance(background)

    lighter = max(first, second)
    darker = min(first, second)

    return (lighter + 0.05) / (darker + 0.05)


class AccessibilityParser(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.findings = []
        self.tags = Counter()
        self.roles = Counter()

        self.images = 0
        self.inputs = 0
        self.labels = 0
        self.focus_issues = 0
        self.invalid_roles = 0
        self.contrast_checked = 0

        self.ids = set()
        self.label_targets = set()
        self.label_stack = []

        self.controls = []
        self.interactive_stack = []

        self.html_found = False

    def add_finding(self, severity, issue, tag=None):
        finding = {
            "severity": severity,
            "issue": issue
        }

        if tag:
            finding["element"] = tag

        self.findings.append(finding)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags[tag] += 1

        element_id = attrs.get("id")

        if element_id:
            self.ids.add(element_id)

        # HTML language attribute
        if tag == "html":
            self.html_found = True

            if not attrs.get("lang"):
                self.add_finding(
                    "MEDIUM",
                    "HTML element is missing the lang attribute.",
                    tag
                )

        # ARIA role validation
        role = attrs.get("role")

        if role:
            role_tokens = role.lower().split()
            valid_role_found = False

            for role_name in role_tokens:
                self.roles[role_name] += 1

                if role_name in VALID_ROLES:
                    valid_role_found = True

            if not valid_role_found:
                self.invalid_roles += 1

                self.add_finding(
                    "MEDIUM",
                    f"Unrecognized ARIA role: {role}.",
                    tag
                )

        # Image alt text
        if tag == "img":
            self.images += 1

            if "alt" not in attrs:
                self.add_finding(
                    "HIGH",
                    "Image is missing its alt attribute.",
                    tag
                )

        # Label association
        if tag == "label":
            self.labels += 1

            label_for = attrs.get("for")

            self.label_stack.append(label_for)

            if label_for:
                self.label_targets.add(label_for)

        # Form controls
        if tag in FORM_CONTROLS:
            input_type = attrs.get("type", "").lower()

            if not (tag == "input" and input_type == "hidden"):
                self.inputs += 1

                control = {
                    "tag": tag,
                    "id": attrs.get("id"),
                    "type": input_type,
                    "attrs": attrs,
                    "wrapped_label": bool(self.label_stack)
                }

                self.controls.append(control)

        # Keyboard accessibility
        if tag in ("div", "span"):
            has_onclick = "onclick" in attrs
            tabindex = attrs.get("tabindex")

            if has_onclick:
                keyboard_focusable = (
                    tabindex is not None
                    and tabindex.strip() != "-1"
                )

                if not keyboard_focusable:
                    self.focus_issues += 1

                    self.add_finding(
                        "MEDIUM",
                        "Clickable div/span may not be keyboard accessible. "
                        "Add keyboard support and a valid tabindex.",
                        tag
                    )

        # Custom interactive ARIA roles
        custom_interactive_roles = {
            "button", "link", "checkbox", "radio",
            "switch", "menuitem", "tab"
        }

        if tag not in INTERACTIVE and tag not in ("a",):
            if role and any(
                item in custom_interactive_roles
                for item in role.lower().split()
            ):
                tabindex = attrs.get("tabindex")

                if tabindex is None or tabindex.strip() == "-1":
                    self.focus_issues += 1

                    self.add_finding(
                        "MEDIUM",
                        "Custom interactive ARIA element may not "
                        "be keyboard focusable.",
                        tag
                    )

        # Accessible names for interactive elements
        is_interactive = (
            tag in INTERACTIVE
            or (tag == "a" and bool(attrs.get("href")))
        )

        if is_interactive:
            if tag == "input" and attrs.get("type", "").lower() == "hidden":
                is_interactive = False

        if is_interactive:
            input_type = attrs.get("type", "").lower()

            has_explicit_name = any(
                attrs.get(key)
                for key in (
                    "aria-label",
                    "aria-labelledby",
                    "title"
                )
            )

            if tag == "input":
                if attrs.get("value"):
                    has_explicit_name = True

                if input_type == "image" and attrs.get("alt"):
                    has_explicit_name = True

            if not has_explicit_name:
                self.interactive_stack.append({
                    "tag": tag,
                    "text": "",
                    "attrs": attrs,
                    "labelled": (
                        attrs.get("id") in self.label_targets
                        or bool(self.label_stack)
                    )
                })

        # Inline CSS contrast checking
        if attrs.get("style"):
            self.check_inline_contrast(attrs["style"], tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if data.strip():
            for item in self.interactive_stack:
                item["text"] += data.strip() + " "

    def handle_endtag(self, tag):

        # Close label context
        if tag == "label" and self.label_stack:
            self.label_stack.pop()

        # Check accessible name
        for index in range(len(self.interactive_stack) - 1, -1, -1):
            item = self.interactive_stack[index]

            if item["tag"] == tag:
                self.interactive_stack.pop(index)

                has_text = bool(item["text"].strip())
                has_label = item["labelled"]

                if not has_text and not has_label:
                    self.add_finding(
                        "MEDIUM",
                        "Interactive element may be missing "
                        "an accessible name.",
                        tag
                    )

                break

    def check_inline_contrast(self, style, tag):
        """Check contrast only when both inline colors are explicit."""
        properties = {}

        for declaration in style.split(";"):
            if ":" not in declaration:
                continue

            key, value = declaration.split(":", 1)

            properties[key.strip().lower()] = value.strip()

        foreground = parse_color(properties.get("color"))
        background = parse_color(
            properties.get("background-color")
        )

        if foreground and background:
            self.contrast_checked += 1

            ratio = contrast_ratio(foreground, background)

            if ratio < 4.5:
                self.add_finding(
                    "HIGH",
                    (
                        f"Inline color contrast ratio is {ratio:.2f}:1. "
                        "WCAG AA normally requires 4.5:1 "
                        "for regular text."
                    ),
                    tag
                )

    def validate_form_labels(self):
        """Validate labels after the entire HTML document is parsed."""
        for control in self.controls:
            attrs = control["attrs"]

            has_accessible_label = (
                bool(attrs.get("aria-label"))
                or bool(attrs.get("aria-labelledby"))
                or bool(attrs.get("title"))
                or control["wrapped_label"]
                or (
                    control["id"] is not None
                    and control["id"] in self.label_targets
                )
            )

            if not has_accessible_label:
                self.add_finding(
                    "HIGH",
                    "Form control is missing an associated label.",
                    control["tag"]
                )


def execute(root):
    root = Path(root).resolve()

    findings = []
    html_files = []

    # Ignore generated reports to prevent self-scanning.
    for path, content in text_files(root):
        relative_parts = path.relative_to(root).parts

        if (
            path.suffix.lower() == ".html"
            and "reports" not in relative_parts
        ):
            html_files.append((path, content))

    if not html_files:
        findings.append({
            "severity": "WARN",
            "issue": "No application HTML files found for accessibility inspection."
        })

    totals = Counter()
    scanned = 0

    for path, content in html_files:
        parser = AccessibilityParser()

        relative = str(path.relative_to(root))

        try:
            parser.feed(content)
            parser.close()
            parser.validate_form_labels()

        except Exception as exc:
            findings.append({
                "severity": "WARN",
                "file": relative,
                "issue": (
                    f"Could not fully parse HTML: "
                    f"{type(exc).__name__}: {exc}"
                )
            })
            continue

        scanned += 1

        totals.update(parser.tags)

        totals["images"] += parser.images
        totals["form_controls"] += parser.inputs
        totals["labels"] += parser.labels
        totals["invalid_roles"] += parser.invalid_roles
        totals["contrast_checks"] += parser.contrast_checked
        totals["focus_issues"] += parser.focus_issues

        for finding in parser.findings:
            finding["file"] = relative
            findings.append(finding)

    status = "WARN" if findings else "PASS"

    summary = (
        f"Scanned {scanned} application HTML files for "
        f"accessibility issues. Found {len(findings)} findings."
    )

    details = {
        "html_files_scanned": scanned,
        "images_checked": totals["images"],
        "form_controls_checked": totals["form_controls"],
        "labels_found": totals["labels"],
        "invalid_aria_roles": totals["invalid_roles"],
        "keyboard_focus_issues": totals["focus_issues"],
        "inline_contrast_checks": totals["contrast_checks"],
        "note": (
            "Static HTML analysis cannot fully evaluate computed browser "
            "contrast, external CSS inheritance, JavaScript-generated "
            "content, or actual keyboard navigation. Full WCAG verification "
            "requires browser-based accessibility testing."
        )
    }

    return result(
        "Accessibility",
        status,
        summary,
        findings,
        details
    )
