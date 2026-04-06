import argparse
import os
import re
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def iter_markdown_files(root: Path, content_dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for d in content_dirs:
        p = (root / d).resolve()
        if not p.exists():
            continue
        for f in p.rglob("*.md"):
            # Skip Obsidian config vault data and other hidden folders
            if any(part.startswith(".") for part in f.parts):
                continue
            files.append(f)
    return files


def build_basename_index(md_files: list[Path], root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for f in md_files:
        rel = f.relative_to(root).as_posix()
        base = f.stem
        index.setdefault(base, []).append(rel)
    return index


def choose_target_path(
    raw_target: str, source_rel_dir: str, basename_index: dict[str, list[str]]
) -> str | None:
    """
    Returns a site-root absolute path (like '/words/foo.html') if resolvable.
    """
    target = raw_target.strip()
    if not target:
        return None

    # Strip Obsidian alias and heading, keep heading as fragment if present.
    # [[path/to/page|Alias]] or [[page|Alias]]
    # [[page#Heading]] or [[page#Heading|Alias]]
    fragment = ""
    if "#" in target:
        target, frag = target.split("#", 1)
        fragment = "#" + frag.strip()
    if "|" in target:
        target, _alias = target.split("|", 1)
    target = target.strip()
    if not target:
        return None

    # If the wikilink includes a slash, treat it as an explicit path from site root.
    if "/" in target:
        site_path = "/" + target.strip("/")
        return site_path + ".html" + fragment

    # Otherwise, try to resolve by filename basename across known content dirs.
    candidates = basename_index.get(target)
    if not candidates:
        return None

    # Prefer same directory as source, then prefer 'words/', then shortest path.
    def score(rel: str) -> tuple[int, int, int]:
        same_dir = 0 if rel.rsplit("/", 1)[0] == source_rel_dir else 1
        prefer_words = 0 if rel.startswith("words/") else 1
        return (same_dir, prefer_words, len(rel))

    best = sorted(candidates, key=score)[0]
    return "/" + best[: -len(".md")] + ".html" + fragment


def replace_wikilinks(text: str, source_rel_dir: str, basename_index: dict[str, list[str]]) -> str:
    def repl(match: re.Match) -> str:
        inner = match.group(1)
        label = inner
        # Display label: Alias if present, else target name without path
        if "|" in inner:
            _target, alias = inner.split("|", 1)
            label = alias.strip() or inner
        else:
            # If [[words/foo]] show 'foo' as label by default
            label = inner.split("#", 1)[0].split("/")[-1].strip() or inner

        href = choose_target_path(inner, source_rel_dir, basename_index)
        if href is None:
            return match.group(0)
        # Use relative_url to respect baseurl on GitHub Pages
        return f"[{label}]({{{{ '{href}' | relative_url }}}})"

    return WIKILINK_RE.sub(repl, text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert Obsidian wikilinks [[...]] to Jekyll-friendly markdown links.")
    ap.add_argument("--root", default=".", help="Repository root")
    ap.add_argument(
        "--content-dirs",
        default="diary,words,books,digitalworks,food,vrchat,_note",
        help="Comma-separated list of content directories to process",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    content_dirs = [d.strip() for d in args.content_dirs.split(",") if d.strip()]

    md_files = iter_markdown_files(root, content_dirs)
    basename_index = build_basename_index(md_files, root)

    changed = 0
    for f in md_files:
        original = f.read_text(encoding="utf-8")
        source_rel_dir = f.relative_to(root).as_posix().rsplit("/", 1)[0]
        updated = replace_wikilinks(original, source_rel_dir, basename_index)
        if updated != original:
            f.write_text(updated, encoding="utf-8")
            changed += 1

    print(f"obsidian_preprocess: updated {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

