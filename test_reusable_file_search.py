"""
Tests for reusable_file_search.py
"""

import subprocess
import sys
from pathlib import Path

import pytest

from reusable_file_search import delete_unused, find_usages, inline_singles, report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPT = Path(__file__).parent / "reusable_file_search.py"


def make_reusable(reusable_dir: Path, name: str, body: str = "") -> Path:
    """Create a reusable Markdown file and return its path."""
    path = reusable_dir / name
    path.write_text(body or f"Reusable content of {name}.\n", encoding="utf-8")
    return path


def make_content(content_dir: Path, name: str, body: str) -> Path:
    """Create a content Markdown file and return its path."""
    path = content_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def shortcode(ref: str) -> str:
    return f'{{{{< readfile file="{ref}" >}}}}'


# ---------------------------------------------------------------------------
# find_usages
# ---------------------------------------------------------------------------


class TestFindUsages:
    def test_single_usage(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "note.md")
        make_content(cd, "page.md", shortcode("content/reusable/note.md"))

        usages, missing = find_usages(rd, cd)

        assert r.as_posix() in usages
        assert len(usages[r.as_posix()]) == 1
        assert missing == set()

    def test_multiple_usages(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "shared.md")
        ref = "content/reusable/shared.md"
        make_content(cd, "page1.md", shortcode(ref))
        make_content(cd, "page2.md", shortcode(ref))
        make_content(cd, "page3.md", shortcode(ref))

        usages, missing = find_usages(rd, cd)

        assert len(usages[r.as_posix()]) == 3
        assert missing == set()

    def test_unused_file_has_zero_count(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "orphan.md")
        make_content(cd, "page.md", "No shortcodes here.\n")

        usages, missing = find_usages(rd, cd)

        assert usages[r.as_posix()] == []

    def test_missing_reference_recorded(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        make_content(cd, "page.md", shortcode("content/reusable/does_not_exist.md"))

        usages, missing = find_usages(rd, cd)

        assert "content/reusable/does_not_exist.md" in missing

    def test_missing_deduplicated(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        ref = "content/reusable/ghost.md"
        make_content(cd, "page1.md", shortcode(ref))
        make_content(cd, "page2.md", shortcode(ref))

        _, missing = find_usages(rd, cd)

        assert missing == {ref}

    def test_multiple_shortcodes_in_one_file(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r1 = make_reusable(rd, "alpha.md")
        r2 = make_reusable(rd, "beta.md")
        body = shortcode("content/reusable/alpha.md") + "\n" + shortcode("content/reusable/beta.md")
        make_content(cd, "page.md", body)

        usages, _ = find_usages(rd, cd)

        assert len(usages[r1.as_posix()]) == 1
        assert len(usages[r2.as_posix()]) == 1

    def test_reusable_files_in_subdirectories(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        sub = rd / "sub"
        sub.mkdir(parents=True); cd.mkdir()

        r = make_reusable(sub, "nested.md")
        make_content(cd, "page.md", shortcode("content/reusable/sub/nested.md"))

        usages, missing = find_usages(rd, cd)

        assert len(usages[r.as_posix()]) == 1
        assert missing == set()


# ---------------------------------------------------------------------------
# inline_singles
# ---------------------------------------------------------------------------


class TestInlineSingles:
    def test_inlines_content_and_deletes_reusable(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        reusable_text = "This is the inlined text.\n"
        r = make_reusable(rd, "tip.md", reusable_text)
        ref = "content/reusable/tip.md"
        content_file = make_content(cd, "page.md", f"Before.\n\n{shortcode(ref)}\n\nAfter.\n")

        usages, _ = find_usages(rd, cd)
        inline_singles(usages)

        assert not r.exists(), "Reusable file should be deleted"
        result = content_file.read_text(encoding="utf-8")
        assert "This is the inlined text." in result
        assert "readfile" not in result

    def test_does_not_inline_multi_use_files(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "shared.md", "Shared.\n")
        ref = "content/reusable/shared.md"
        make_content(cd, "page1.md", shortcode(ref))
        make_content(cd, "page2.md", shortcode(ref))

        usages, _ = find_usages(rd, cd)
        inline_singles(usages)

        assert r.exists(), "Multi-use reusable file should NOT be deleted"

    def test_does_not_inline_unused_files(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "unused.md", "Unused.\n")
        make_content(cd, "page.md", "No shortcodes.\n")

        usages, _ = find_usages(rd, cd)
        inline_singles(usages)

        assert r.exists(), "Unused reusable file should NOT be touched by inline_singles"

    def test_no_candidates_produces_no_error(self, tmp_path, capsys):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        make_content(cd, "page.md", "No shortcodes.\n")
        usages, _ = find_usages(rd, cd)
        inline_singles(usages)  # should not raise

        out = capsys.readouterr().out
        assert "Nothing to inline" in out


# ---------------------------------------------------------------------------
# delete_unused
# ---------------------------------------------------------------------------


class TestDeleteUnused:
    def test_deletes_unreferenced_file(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "orphan.md")
        make_content(cd, "page.md", "No shortcodes.\n")

        usages, _ = find_usages(rd, cd)
        delete_unused(usages)

        assert not r.exists()

    def test_does_not_delete_used_file(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "used.md")
        make_content(cd, "page.md", shortcode("content/reusable/used.md"))

        usages, _ = find_usages(rd, cd)
        delete_unused(usages)

        assert r.exists()

    def test_no_unused_produces_no_error(self, tmp_path, capsys):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        r = make_reusable(rd, "used.md")
        make_content(cd, "page.md", shortcode("content/reusable/used.md"))

        usages, _ = find_usages(rd, cd)
        delete_unused(usages)

        out = capsys.readouterr().out
        assert "Nothing to delete" in out
        assert r.exists()

    def test_deletes_only_unreferenced_among_mixed(self, tmp_path):
        rd = tmp_path / "reusable"
        cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()

        used = make_reusable(rd, "used.md")
        unused = make_reusable(rd, "unused.md")
        make_content(cd, "page.md", shortcode("content/reusable/used.md"))

        usages, _ = find_usages(rd, cd)
        delete_unused(usages)

        assert used.exists()
        assert not unused.exists()


# ---------------------------------------------------------------------------
# report output
# ---------------------------------------------------------------------------


class TestReport:
    def _run_report(self, usages, missing, **kwargs):
        report(usages, missing, **kwargs)

    def test_alert_shown_for_zero_use(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_reusable(rd, "orphan.md")
        make_content(cd, "page.md", "No shortcodes.\n")
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing)
        out = capsys.readouterr().out
        assert "[ALERT]" in out

    def test_ok_shown_when_all_used_multiple_times(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        r = make_reusable(rd, "shared.md")
        ref = "content/reusable/shared.md"
        make_content(cd, "page1.md", shortcode(ref))
        make_content(cd, "page2.md", shortcode(ref))
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing)
        out = capsys.readouterr().out
        assert "[OK] All reusable files are used more than once" in out

    def test_missing_section_shown_with_flag(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_content(cd, "page.md", shortcode("content/reusable/ghost.md"))
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing, show_missing=True)
        out = capsys.readouterr().out
        assert "[MISSING]" in out
        assert "ghost.md" in out

    def test_missing_section_hidden_without_flag(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_content(cd, "page.md", shortcode("content/reusable/ghost.md"))
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing, show_missing=False)
        out = capsys.readouterr().out
        assert "[MISSING]" not in out

    def test_locations_shown_with_flag(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_reusable(rd, "tip.md")
        cp = make_content(cd, "page.md", shortcode("content/reusable/tip.md"))
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing, show_locations=True)
        out = capsys.readouterr().out
        assert cp.as_posix() in out

    def test_locations_hidden_without_flag(self, tmp_path, capsys):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_reusable(rd, "tip.md")
        cp = make_content(cd, "page.md", shortcode("content/reusable/tip.md"))
        usages, missing = find_usages(rd, cd)
        self._run_report(usages, missing, show_locations=False)
        out = capsys.readouterr().out
        assert cp.as_posix() not in out


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def _run(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_basic_run(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_reusable(rd, "note.md")
        make_content(cd, "page.md", shortcode("content/reusable/note.md"))
        result = self._run(str(rd), str(cd))
        assert result.returncode == 0
        assert "Reusable file audit" in result.stdout

    def test_invalid_reusable_dir_exits(self, tmp_path):
        cd = tmp_path / "content"; cd.mkdir()
        result = self._run(str(tmp_path / "nonexistent"), str(cd))
        assert result.returncode != 0

    def test_invalid_content_dir_exits(self, tmp_path):
        rd = tmp_path / "reusable"; rd.mkdir()
        result = self._run(str(rd), str(tmp_path / "nonexistent"))
        assert result.returncode != 0

    def test_show_locations_flag(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_reusable(rd, "note.md")
        cp = make_content(cd, "page.md", shortcode("content/reusable/note.md"))
        result = self._run(str(rd), str(cd), "--show-locations")
        assert cp.as_posix() in result.stdout

    def test_show_missing_flag(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        make_content(cd, "page.md", shortcode("content/reusable/ghost.md"))
        result = self._run(str(rd), str(cd), "--show-missing")
        assert "[MISSING]" in result.stdout
        assert "ghost.md" in result.stdout

    def test_inline_singles_flag(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        r = make_reusable(rd, "tip.md", "Inlined tip.\n")
        make_content(cd, "page.md", shortcode("content/reusable/tip.md"))
        result = self._run(str(rd), str(cd), "--inline-singles")
        assert result.returncode == 0
        assert not r.exists()

    def test_delete_unused_flag(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        r = make_reusable(rd, "orphan.md")
        make_content(cd, "page.md", "No shortcodes.\n")
        result = self._run(str(rd), str(cd), "--delete-unused")
        assert result.returncode == 0
        assert not r.exists()

    def test_delete_unused_preserves_used_files(self, tmp_path):
        rd = tmp_path / "reusable"; cd = tmp_path / "content"
        rd.mkdir(); cd.mkdir()
        r = make_reusable(rd, "used.md")
        make_content(cd, "page.md", shortcode("content/reusable/used.md"))
        result = self._run(str(rd), str(cd), "--delete-unused")
        assert result.returncode == 0
        assert r.exists()
