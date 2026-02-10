#!/usr/bin/env python3
"""Apply size-optimization edits to the Feishin upstream source tree.

Usage:
  python tools/feishin_optimize.py /path/to/feishin
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.request import urlopen

REACT_ICON_IMPORT_RE = re.compile(
    r"^import\s+(?:type\s+)?{\s*(?P<names>[^}]+)\s*}\s*from\s*['\"]react-icons/(?P<pack>[^'\"/]+)['\"];?\s*(?:\/\/.*)?$",
    re.MULTILINE,
)


def update_electron_builder(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    content = content.replace(
        "asarUnpack:\n    - resources/**\n",
        "asarUnpack:\n    - resources/**/*.node\n    - resources/**/*.dll\n    - resources/**/*.so\n    - resources/**/*.dylib\n    - node_modules/abstract-socket/**\n",
    )
    if "# consider dropping AppImage" not in content:
        content = content.replace(
            "- tar.xz\n",
            "- tar.xz\n    # consider dropping AppImage when size is a priority\n",
        )
    if content != original:
        path.write_text(content, encoding="utf-8")
        return True
    return False


def update_electron_vite(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    content = re.sub(r"sourcemap: true", "sourcemap: false", content)

    # Switch to rolldownOptions and ensure renderer input + treeshake exist.
    content = re.sub(r"rollupOptions", "rolldownOptions", content)
    if "renderer:" in content and "rolldownOptions:" in content:
        content = re.sub(
            r"(renderer:\s*{[\s\S]*?build:\s*{[\s\S]*?minify: 'esbuild',)\s*\n\s*rolldownOptions:\s*{[\s\S]*?}\s*,",
            r"\1\n            rolldownOptions: {\n                input: {\n                    index: resolve('src/renderer/index.html'),\n                },\n                treeshake: true,\n            },",
            content,
            count=1,
        )
    if "treeshake:" not in content and "renderer:" in content:
        content = re.sub(
            r"(renderer:\s*{[\s\S]*?build:\s*{[\s\S]*?minify: 'esbuild',)",
            r"\1\n            rolldownOptions: {\n                input: {\n                    index: resolve('src/renderer/index.html'),\n                },\n                treeshake: true,\n            },",
            content,
            count=1,
        )

    # Ensure main external includes electron, source-map-support, and x11.
    content = re.sub(
        r"external:\s*\[(.*?)\]",
        lambda m: _ensure_external_list(m.group(0), ["electron", "source-map-support", "x11"]),
        content,
        count=1,
    )

    if content != original:
        path.write_text(content, encoding="utf-8")
        return True
    return False


def _ensure_external_list(external_line: str, required: list[str]) -> str:
    if not external_line.endswith("]"):
        return external_line
    for name in required:
        if name not in external_line:
            external_line = external_line[:-1] + f", '{name}']"
    return external_line


def update_remote_vite(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    original = content
    content = re.sub(r"sourcemap: true", "sourcemap: false", content)

    # Switch to rolldownOptions for Vite 7.x usage.
    content = re.sub(r"rollupOptions", "rolldownOptions", content)

    if content != original:
        path.write_text(content, encoding="utf-8")
        return True
    return False


def _resolve_react_icons_version(data: dict) -> str | None:
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section, {})
        if "react-icons" in deps:
            return deps["react-icons"]
    return None


def _extract_semver(version: str) -> str | None:
    match = re.search(r"\d+\.\d+\.\d+", version)
    if match:
        return match.group(0)
    return None


def _find_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "\"":
                in_string = False
            continue
        if char == "\"":
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _insert_dependency(text: str, name: str, version: str) -> tuple[str, bool]:
    match = re.search(r"\"dependencies\"\s*:\s*{", text)
    if not match:
        return text, False
    object_start = text.find("{", match.end() - 1)
    if object_start == -1:
        return text, False
    object_end = _find_object_end(text, object_start)
    if object_end is None:
        return text, False

    before = text[:object_start + 1]
    body = text[object_start + 1 : object_end]
    after = text[object_end:]

    dep_line_match = re.search(r"\n(\s*)\"dependencies\"", text[:object_start])
    base_indent = dep_line_match.group(1) if dep_line_match else ""
    entry_indent_match = re.search(r"\n(\s*)\"[^\"]+\"\s*:", body)
    if entry_indent_match:
        item_indent = entry_indent_match.group(1)
    else:
        item_indent = base_indent + "  "

    body_stripped = body.strip()
    if body_stripped:
        needs_comma = not body_stripped.rstrip().endswith(",")
        separator = "," if needs_comma else ""
        insertion = f"{separator}\n{item_indent}\"{name}\": \"{version}\""
        new_body = body.rstrip() + insertion + "\n" + base_indent
    else:
        new_body = f"\n{item_indent}\"{name}\": \"{version}\"\n{base_indent}"
    return before + new_body + after, True


def _remove_dependency(text: str, section: str, name: str) -> tuple[str, bool]:
    pattern = rf"(\"{re.escape(section)}\"\\s*:\\s*{{)(?P<body>.*?)(\\s*}})"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return text, False

    body = match.group("body")
    lines = body.splitlines()
    removed = False
    new_lines = []
    entry_pattern = re.compile(rf"\\s*\"{re.escape(name)}\"\\s*:")

    for line in lines:
        if entry_pattern.match(line):
            removed = True
            continue
        new_lines.append(line)

    if removed:
        for i in range(len(new_lines) - 1, -1, -1):
            if new_lines[i].strip():
                new_lines[i] = re.sub(r",\\s*$", "", new_lines[i])
                break
        new_body = "\n".join(new_lines)
        updated = text[: match.start("body")] + new_body + text[match.end("body") :]
        return updated, True

    return text, False


def _force_remove_dependency(text: str, section: str, name: str) -> tuple[str, bool]:
    pattern = rf"(\"{re.escape(section)}\"\\s*:\\s*{{)(?P<body>.*?)(\\s*}})"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return text, False

    body = match.group("body")
    lines = body.splitlines()
    removed = False
    new_lines = []
    entry_pattern = re.compile(rf"\\s*\"{re.escape(name)}\"\\s*:")

    for line in lines:
        if entry_pattern.match(line):
            removed = True
            continue
        new_lines.append(line)

    if not removed:
        return text, False

    for i in range(len(new_lines) - 1, -1, -1):
        if new_lines[i].strip():
            new_lines[i] = re.sub(r",\\s*$", "", new_lines[i])
            break

    new_body = "\n".join(new_lines)
    updated = text[: match.start("body")] + new_body + text[match.end("body") :]
    return updated, True


def _remove_dependency_line(text: str, name: str) -> tuple[str, bool]:
    pattern = rf"^\s*\"{re.escape(name)}\"\s*:\s*\"[^\"]+\"\s*,?\s*\n"
    updated, count = re.subn(pattern, "", text, flags=re.MULTILINE)
    return updated, count > 0


def _fix_section_last_comma(text: str, section: str) -> str:
    pattern = rf"(\"{re.escape(section)}\"\s*:\s*{{)(?P<body>.*?)(\n\s*}})"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return text
    body_lines = match.group("body").splitlines()
    for i in range(len(body_lines) - 1, -1, -1):
        if body_lines[i].strip():
            body_lines[i] = re.sub(r",\s*$", "", body_lines[i])
            break
    new_body = "\n".join(body_lines)
    return text[: match.start("body")] + new_body + text[match.end("body") :]


def update_package_json(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    deps = data.get("dependencies", {})
    dev_deps = data.get("devDependencies", {})
    has_all_files_dep = "@react-icons/all-files" in deps
    has_all_files_dev = "@react-icons/all-files" in dev_deps
    react_icons_version = _resolve_react_icons_version(data)
    desired_version = None
    if react_icons_version:
        semver = _extract_semver(react_icons_version)
        if semver:
            desired_version = (
                "https://github.com/react-icons/react-icons/releases/download/"
                f"v{semver}/react-icons-all-files-{semver}.tgz"
            )

    updated = raw
    changed = False

    # Move @react-icons/all-files to devDependencies.
    if has_all_files_dep:
        updated, removed_dep = _remove_dependency(updated, "dependencies", "@react-icons/all-files")
        changed = changed or removed_dep
    if not has_all_files_dev and desired_version:
        updated, inserted = _insert_dev_dependency(
            updated, "@react-icons/all-files", desired_version
        )
        changed = changed or inserted

    # Remove react-icons from both dependencies and devDependencies.
    updated, removed_deps = _remove_dependency(updated, "dependencies", "react-icons")
    changed = changed or removed_deps
    updated, removed_dev = _remove_dependency(updated, "devDependencies", "react-icons")
    changed = changed or removed_dev
    updated, forced_deps = _force_remove_dependency(updated, "dependencies", "react-icons")
    changed = changed or forced_deps
    updated, forced_dev = _force_remove_dependency(updated, "devDependencies", "react-icons")
    changed = changed or forced_dev
    updated, removed_anywhere = _remove_dependency_line(updated, "react-icons")
    changed = changed or removed_anywhere
    if removed_anywhere:
        updated = _fix_section_last_comma(updated, "dependencies")
        updated = _fix_section_last_comma(updated, "devDependencies")

    # Switch to rolldown-vite when vite is 7.x.
    updated, switched_vite = _switch_vite_to_rolldown(updated)
    changed = changed or switched_vite

    if changed:
        path.write_text(updated, encoding="utf-8")
    return changed


def _insert_dev_dependency(text: str, name: str, version: str | None = None) -> tuple[str, bool]:
    match = re.search(r"\"devDependencies\"\s*:\s*{", text)
    if not match:
        return text, False
    object_start = text.find("{", match.end() - 1)
    if object_start == -1:
        return text, False
    object_end = _find_object_end(text, object_start)
    if object_end is None:
        return text, False

    before = text[:object_start + 1]
    body = text[object_start + 1 : object_end]
    after = text[object_end:]

    dep_line_match = re.search(r"\n(\s*)\"devDependencies\"", text[:object_start])
    base_indent = dep_line_match.group(1) if dep_line_match else ""
    entry_indent_match = re.search(r"\n(\s*)\"[^\"]+\"\s*:", body)
    if entry_indent_match:
        item_indent = entry_indent_match.group(1)
    else:
        item_indent = base_indent + "  "

    if version is None:
        version = "*"

    body_stripped = body.strip()
    if body_stripped:
        needs_comma = not body_stripped.rstrip().endswith(",")
        separator = "," if needs_comma else ""
        insertion = f"{separator}\n{item_indent}\"{name}\": \"{version}\""
        new_body = body.rstrip() + insertion + "\n" + base_indent
    else:
        new_body = f"\n{item_indent}\"{name}\": \"{version}\"\n{base_indent}"
    return before + new_body + after, True


def _switch_vite_to_rolldown(text: str) -> tuple[str, bool]:
    match = re.search(
        r"\"devDependencies\"\s*:\s*{[\s\S]*?\"vite\"\s*:\s*\"(?P<version>[^\"]+)\"",
        text,
    )
    if not match:
        return text, False
    if not re.match(r"^\^?7\.", match.group("version")):
        return text, False
    target_version = _resolve_rolldown_vite_7x() or "7"
    updated = re.sub(
        r"\"vite\"\s*:\s*\"[^\"]+\"",
        f'"vite": "npm:rolldown-vite@{target_version}"',
        text,
        count=1,
    )
    return updated, updated != text


def _resolve_rolldown_vite_7x() -> str | None:
    try:
        with urlopen("https://registry.npmjs.org/rolldown-vite", timeout=10) as resp:
            data = json.load(resp)
    except Exception:
        return None

    versions = data.get("versions", {})
    best: tuple[int, int, int, str] | None = None
    for version in versions:
        match = re.match(r"^(?P<major>7)\.(?P<minor>\d+)\.(?P<patch>\d+)$", version)
        if not match:
            continue
        current = (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            version,
        )
        if best is None or current[:3] > best[:3]:
            best = current

    if not best:
        return None
    return best[3]


def update_react_icon_imports(root: Path, verbose: bool = False) -> int:
    count = 0
    for path in root.rglob("*.ts"):
        count += _update_react_icon_file(path, verbose=verbose)
    for path in root.rglob("*.tsx"):
        count += _update_react_icon_file(path, verbose=verbose)
    return count


IPC_IDEMPOTENCY_ALLOWLIST = [
    r"^settings-get$",
    r"^password-get$",
    r"^password-set$",
    r"^open-file-selector$",
]


def update_ipc_idempotency(root: Path, verbose: bool = False) -> int:
    count = 0
    for path in (root / "src" / "main").rglob("*.ts"):
        count += _update_ipc_idempotency_file(path, verbose=verbose)
    return count


def _update_ipc_idempotency_file(path: Path, verbose: bool = False) -> int:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    updated_lines: list[str] = []
    changed = False

    handle_re = re.compile(r"^\s*ipcMain\.handle\(\s*(['\"])(?P<channel>[^'\"]+)\1")
    on_re = re.compile(r"^\s*ipcMain\.on\(\s*(['\"])(?P<channel>[^'\"]+)\1")

    for line in lines:
        handle_match = handle_re.match(line)
        on_match = on_re.match(line)
        if handle_match:
            channel = handle_match.group("channel")
            if not _ipc_channel_allowed(channel):
                updated_lines.append(line)
                continue
            if not _has_prior_guard(updated_lines, "ipcMain.removeHandler", channel):
                updated_lines.append(f"ipcMain.removeHandler('{channel}');")
                changed = True
        elif on_match:
            channel = on_match.group("channel")
            if not _ipc_channel_allowed(channel):
                updated_lines.append(line)
                continue
            if not _has_prior_guard(updated_lines, "ipcMain.removeAllListeners", channel):
                updated_lines.append(f"ipcMain.removeAllListeners('{channel}');")
                changed = True
        updated_lines.append(line)

    if changed:
        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        if verbose:
            print(f"ipcMain idempotency: {path}")
        return 1
    return 0


def _has_prior_guard(lines: list[str], guard: str, channel: str) -> bool:
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip() == "":
            continue
        return f"{guard}('{channel}')" in lines[idx]
    return False


def _ipc_channel_allowed(channel: str) -> bool:
    return any(re.search(pattern, channel) for pattern in IPC_IDEMPOTENCY_ALLOWLIST)


def _rewrite_react_icon_imports(content: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        pack = match.group("pack")
        names = match.group("names")
        imports = []
        for entry in names.split(","):
            entry = entry.strip()
            if not entry:
                continue
            if " as " in entry:
                original, alias = [part.strip() for part in entry.split(" as ", 1)]
                spec = f"{original} as {alias}"
            else:
                original = entry
                spec = original
            imports.append(
                f"import {{ {spec} }} from \"@react-icons/all-files/{pack}/{original}\";"
            )
        return "\n".join(imports)

    updated = REACT_ICON_IMPORT_RE.sub(replacer, content)
    return updated


def _update_react_icon_file(path: Path, verbose: bool = False) -> int:
    content = path.read_text(encoding="utf-8")
    updated = _rewrite_react_icon_imports(content)
    if updated != content:
        path.write_text(updated, encoding="utf-8")
        if verbose:
            print(f"react-icons rewrite: {path}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Path to the Feishin source root")
    parser.add_argument("--verbose", action="store_true", help="Log each file rewritten")
    args = parser.parse_args()

    root = args.source
    builder_changed = update_electron_builder(root / "electron-builder.yml")
    vite_changed = update_electron_vite(root / "electron.vite.config.ts")
    remote_changed = update_remote_vite(root / "remote.vite.config.ts")
    pkg_changed = update_package_json(root / "package.json")
    icon_files_changed = update_react_icon_imports(root, verbose=args.verbose)
    ipc_files_changed = update_ipc_idempotency(root, verbose=args.verbose)

    print("electron-builder.yml updated:", builder_changed)
    print("electron.vite.config.ts updated:", vite_changed)
    print("remote.vite.config.ts updated:", remote_changed)
    print("package.json updated:", pkg_changed)
    print("react-icons files updated:", icon_files_changed)
    print("ipcMain idempotency files updated:", ipc_files_changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
