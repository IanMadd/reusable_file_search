"""
Audit Hugo readfile shortcode usage across a content directory.

Usage:
    python reusable_file_search.py <reusable_dir> <content_dir> [--show-locations] [--show-missing]

Arguments:
    reusable_dir      Directory containing reusable Markdown files.
    content_dir       Directory containing content Markdown files that use readfile.
    --show-locations  Optional flag to show where each reusable file is used.
    --show-missing    Optional flag to list referenced reusable files that do not exist on disk.
    --inline-singles  For each reusable file used exactly once, replace its readfile shortcode
                      with the file's content, then delete the reusable file.
    --delete-unused   Delete reusable Markdown files that are not referenced in any content file.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path


READFILE_PATTERN = re.compile(r'{{<\s*readfile\s+file\s*=\s*"([^"]+)"\s*>}}')


def find_usages(
    reusable_dir: Path, content_dir: Path
) -> tuple[dict[str, list[str]], set[str]]:
    """
    Scan content_dir for readfile shortcodes that reference files in reusable_dir.

    Returns:
        usages  - dict mapping each known reusable file path to a list of content
                  files that reference it.
        missing - set of shortcode paths that were referenced in content files but
                  could not be matched to any file in reusable_dir.
    """
    # Collect all reusable files and normalise their paths as they appear in shortcodes.
    reusable_files: dict[str, Path] = {}
    for f in reusable_dir.rglob("*.md"):
        # Hugo readfile paths are typically relative to the project root (content/).
        # Store both the full path and a normalised string for matching.
        reusable_files[f.as_posix()] = f

    usages: dict[str, list[str]] = defaultdict(list)
    missing: set[str] = set()

    # Pre-populate every known reusable file so files with zero uses still appear.
    for key in reusable_files:
        usages.setdefault(key, [])

    # Walk every Markdown file in the content directory.
    for content_file in content_dir.rglob("*.md"):
        try:
            text = content_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  WARNING: could not read {content_file}: {exc}", file=sys.stderr)
            continue

        for match in READFILE_PATTERN.finditer(text):
            ref = match.group(1)  # e.g. "content/reusable/md/some_file.md"

            # Try to resolve the referenced path against known reusable files.
            # Match on the suffix of the path so drive/root differences don't matter.
            matched_key = None
            for key in reusable_files:
                if key.endswith(ref) or ref.endswith(key):
                    matched_key = key
                    break
                # Also try matching just the filename portion as a fallback.
                if Path(ref).name == Path(key).name:
                    matched_key = key
                    break

            if matched_key is not None:
                usages[matched_key].append(content_file.as_posix())
            else:
                # Reference not found among known reusable files — record as missing.
                missing.add(ref)

    return usages, missing


def inline_singles(usages: dict[str, list[str]]) -> None:
    """
    For each reusable file used exactly once, inline its content into the referencing
    content file (replacing the readfile shortcode), then delete the reusable file.
    """
    candidates = {k: v for k, v in usages.items() if len(v) == 1}

    if not candidates:
        print("\n[INLINE] No reusable files are used exactly once. Nothing to inline.")
        return

    print(f"\n[INLINE] Inlining {len(candidates)} file(s) used exactly once:\n")

    for reusable_key, locations in sorted(candidates.items()):
        reusable_path = Path(reusable_key)
        content_file = Path(locations[0])

        if not reusable_path.exists():
            print(f"  [SKIP] Reusable file not found on disk: {reusable_key}")
            continue

        try:
            reusable_text = reusable_path.read_text(encoding="utf-8")
            content_text = content_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  [ERROR] Could not read file: {exc}")
            continue

        # Replace the matching shortcode with the reusable file's content.
        replaced = False

        def make_replacer(key: str, path: Path) -> re.Pattern:
            def replacer(m: re.Match) -> str:
                nonlocal replaced
                ref = m.group(1)
                if key.endswith(ref) or ref.endswith(key) or Path(ref).name == path.name:
                    replaced = True
                    return reusable_text.rstrip("\n")
                return m.group(0)
            return replacer

        new_content = READFILE_PATTERN.sub(make_replacer(reusable_key, reusable_path), content_text)

        if not replaced:
            print(f"  [SKIP] Could not locate matching shortcode in: {locations[0]}")
            continue

        try:
            content_file.write_text(new_content, encoding="utf-8")
            reusable_path.unlink()
            print(f"  [OK]   {reusable_key}")
            print(f"         inlined into: {locations[0]}")
            print(f"         Reusable file deleted.")
        except OSError as exc:
            print(f"  [ERROR] File operation failed: {exc}")


def delete_unused(usages: dict[str, list[str]]) -> None:
    """
    Delete every reusable file that has zero references in the content directory.
    """
    unused = {k: v for k, v in usages.items() if len(v) == 0}

    if not unused:
        print("\n[DELETE-UNUSED] No unused reusable files found. Nothing to delete.")
        return

    print(f"\n[DELETE-UNUSED] Deleting {len(unused)} unused file(s):\n")

    for reusable_key in sorted(unused):
        reusable_path = Path(reusable_key)
        if not reusable_path.exists():
            print(f"  [SKIP] File not found on disk: {reusable_key}")
            continue
        try:
            reusable_path.unlink()
            print(f"  [OK]   Deleted: {reusable_key}")
        except OSError as exc:
            print(f"  [ERROR] Could not delete {reusable_key}: {exc}")


def report(
    usages: dict[str, list[str]],
    missing: set[str],
    show_locations: bool = False,
    show_missing: bool = False,
) -> None:
    """Print an audit report to stdout."""
    errors: list[tuple[str, list[str]]] = []
    info: list[tuple[str, list[str]]] = []

    for file_path, locations in sorted(usages.items()):
        count = len(locations)
        if count <= 1:
            errors.append((file_path, locations))
        else:
            info.append((file_path, locations))

    # ------------------------------------------------------------------ #
    # Summary section                                                      #
    # ------------------------------------------------------------------ #
    total = len(usages)
    print(f"\nReusable file audit — {total} file(s) found\n")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # Error / warning section                                              #
    # ------------------------------------------------------------------ #
    if errors:
        print(f"\n[ALERT] {len(errors)} file(s) used 0 or 1 time(s):\n")
        for file_path, locations in errors:
            count = len(locations)
            label = "0 uses" if count == 0 else "1 use"
            print(f"  [!] {file_path}  ({label})")
            if show_locations and locations:
                for loc in locations:
                    print(f"        -> {loc}")
    else:
        print("\n[OK] All reusable files are used more than once.")

    # ------------------------------------------------------------------ #
    # Missing files section                                                #
    # ------------------------------------------------------------------ #
    if show_missing:
        if missing:
            print(f"\n[MISSING] {len(missing)} referenced file(s) not found on disk:\n")
            for ref in sorted(missing):
                print(f"  [?] {ref}")
        else:
            print("\n[OK] All referenced reusable files exist on disk.")

    # ------------------------------------------------------------------ #
    # Usage counts                                                         #
    # ------------------------------------------------------------------ #
    print(f"\n{'File':<55} {'Uses':>5}")
    print("-" * 62)
    for file_path, locations in sorted(usages.items(), key=lambda x: -len(x[1])):
        count = len(locations)
        print(f"  {file_path:<53} {count:>5}")
        if show_locations and locations:
            for loc in sorted(set(locations)):
                print(f"      -> {loc}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Hugo readfile shortcode usage across a content directory."
    )
    parser.add_argument(
        "reusable_dir",
        help="Directory containing reusable Markdown files (e.g. content/reusable/md/).",
    )
    parser.add_argument(
        "content_dir",
        help="Directory containing content Markdown files that use readfile shortcodes.",
    )
    parser.add_argument(
        "--show-locations",
        action="store_true",
        default=False,
        help="Show which content files reference each reusable file.",
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        default=False,
        help="List reusable files referenced in content but not found on disk.",
    )
    parser.add_argument(
        "--inline-singles",
        action="store_true",
        default=False,
        help=(
            "For each reusable file used exactly once, replace its readfile shortcode "
            "with the file's content, then delete the reusable file."
        ),
    )
    parser.add_argument(
        "--delete-unused",
        action="store_true",
        default=False,
        help="Delete reusable Markdown files that are not referenced in any content file.",
    )
    args = parser.parse_args()

    reusable_dir = Path(args.reusable_dir).expanduser().resolve()
    content_dir = Path(args.content_dir).expanduser().resolve()

    for label, path in [("reusable_dir", reusable_dir), ("content_dir", content_dir)]:
        if not path.is_dir():
            print(f"ERROR: {label} is not a valid directory: {path}", file=sys.stderr)
            sys.exit(1)

    usages, missing = find_usages(reusable_dir, content_dir)
    report(usages, missing, show_locations=args.show_locations, show_missing=args.show_missing)
    if args.inline_singles:
        inline_singles(usages)
    if args.delete_unused:
        delete_unused(usages)


if __name__ == "__main__":
    main()
