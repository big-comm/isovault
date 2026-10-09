"""Tests for HTMLGenerator."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from tests.factories import make_file
from services.html_generator import HTMLGenerator

HASH = "d41d8cd98f00b204e9800998ecf8427e"


@pytest.fixture
def generator():
    return HTMLGenerator(lambda key: f"https://cdn.example.com/{key}", lang="en")


def cards(page):
    return re.findall(r'<div class="file-card".*?</a>', page, re.S)


class TestPageStructure:
    def test_all_placeholders_substituted(self, generator):
        page = generator.generate_main_index([make_file("a.iso")], {})
        assert not re.search(r"\$[a-z_]+", page)
        assert page.startswith("<!DOCTYPE html>")
        assert page.rstrip().endswith("</html>")

    def test_css_and_js_inlined(self, generator):
        page = generator.generate_main_index([], {})
        assert "--bg-primary" in page
        assert "lucide.createIcons()" in page

    def test_lucide_is_pinned_with_integrity(self, generator):
        page = generator.generate_main_index([], {})
        assert "lucide@latest" not in page
        assert re.search(r'lucide@\d+\.\d+\.\d+/.*integrity="sha384-', page, re.S)

    def test_icon_rules_target_rendered_svgs(self):
        """Lucide replaces <i> with <svg class="lucide">, so CSS must not select the <i> tag."""
        from services.html_generator import _read_template

        assert not re.search(r"(^|[\s,])i\s*[{,]", _read_template("index.css"), re.M)

    def test_lang_attribute(self):
        page = HTMLGenerator(str, lang="pt-BR").generate_main_index([], {})
        assert '<html lang="pt-BR">' in page

    def test_no_inline_event_handlers(self, generator):
        page = generator.generate_main_index([make_file("a.iso"), make_file("a.iso.md5")], {"a.iso.md5": HASH})
        assert "onclick" not in page


class TestMainIndex:
    def test_sections_root_first_and_only_with_isos(self, generator):
        files = [
            make_file("XFCE/x.iso"),
            make_file("Gnome/g.iso"),
            make_file("r.iso"),
            make_file("Cinnamon/orphan.md5"),
        ]
        page = generator.generate_main_index(files, {})
        headings = re.findall(r"<h2>(.*?)</h2>", page)
        assert headings == ["Root", "Gnome", "XFCE"]

    def test_counts(self, generator):
        files = [make_file("Gnome/a.iso"), make_file("Gnome/b.iso"), make_file("c.iso")]
        page = generator.generate_main_index(files, {})
        assert "<strong>3</strong>" in page
        assert len(cards(page)) == 3

    def test_empty_state(self, generator):
        page = generator.generate_main_index([make_file("orphan.md5")], {})
        assert 'class="empty-state"' in page
        assert cards(page) == []

    def test_timestamp_is_really_utc(self, generator):
        local = datetime(2026, 1, 1, 9, 30, tzinfo=timezone(timedelta(hours=-3)))
        page = generator.generate_main_index([], {}, updated_at=local)
        assert "2026-01-01 12:30 UTC" in page

    def test_download_link(self, generator):
        page = generator.generate_main_index([make_file("Gnome/a.iso")], {})
        assert 'href="https://cdn.example.com/Gnome/a.iso"' in page


class TestFolderIndex:
    def test_lists_folder_isos(self, generator):
        page = generator.generate_folder_index("XFCE", [make_file("XFCE/a.iso")], {})
        assert len(cards(page)) == 1
        assert 'href="../"' in page
        assert "<title>XFCE - BigCommunity ISO Repository</title>" in page

    def test_empty_folder(self, generator):
        page = generator.generate_folder_index("XFCE", [], {})
        assert 'class="empty-state"' in page


class TestMD5:
    def test_hash_from_file_content(self, generator):
        files = [make_file("a.iso"), make_file("a.iso.md5")]
        page = generator.generate_main_index(files, {"a.iso.md5": f"{HASH.upper()}  a.iso\n"})
        assert f'data-md5="{HASH}"' in page
        assert f'<span class="md5-hash">{HASH}</span>' in page

    @pytest.mark.parametrize("hashes", [{}, {"a.md5": ""}, {"a.md5": "not a checksum"}])
    def test_no_section_without_a_valid_hash(self, generator, hashes):
        files = [make_file("a.iso"), make_file("a.md5")]
        assert 'class="md5-section"' not in generator.generate_main_index(files, hashes)

    def test_md5_attached_to_the_right_iso(self, generator):
        """Regression: "big.md5" used to be shown under "big-xfce.iso"."""
        files = [make_file("big-xfce.iso"), make_file("big.md5"), make_file("big.iso")]
        page = generator.generate_main_index(files, {"big.md5": HASH})
        by_name = {re.search(r'data-filename="(.*?)"', c).group(1): c for c in cards(page)}
        assert HASH in by_name["big.iso"]
        assert HASH not in by_name["big-xfce.iso"]

    def test_invalid_content_is_not_rendered(self, generator):
        """Regression: non-hash content ended up inside an inline onclick handler."""
        files = [make_file("a.iso"), make_file("a.iso.md5")]
        page = generator.generate_main_index(files, {"a.iso.md5": "x');alert(1);//"})
        assert "alert" not in page
        assert 'class="md5-section"' not in page


class TestEscaping:
    def test_file_name(self, generator):
        page = generator.generate_main_index([make_file('<img src=x onerror="a">.iso')], {})
        assert "<img" not in page
        assert "&lt;img src=x onerror=&quot;a&quot;&gt;.iso" in page

    def test_url_attribute(self):
        generator = HTMLGenerator(lambda key: f'https://x/"><script>{key}', lang="en")
        page = generator.generate_main_index([make_file("a.iso")], {})
        assert "<script>a.iso" not in page

    def test_folder_name(self, generator):
        page = generator.generate_folder_index("<b>", [], {})
        assert "<b>" not in page
        assert "&lt;b&gt;" in page
