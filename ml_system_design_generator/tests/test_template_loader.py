"""Tests for template_loader tool."""

import pytest

from ml_system_design_generator.tools.template_loader import (
    VALID_STYLES,
    get_style_max_pages,
    get_style_sections,
    list_available_styles,
    load_style_template,
    summarize_style,
)


class TestLoadStyleTemplate:
    def test_load_amazon_6page(self):
        template = load_style_template("amazon_6page")
        assert template["name"] == "Amazon 6-Page Narrative Memo"
        assert "sections" in template
        assert len(template["sections"]) >= 7

    def test_load_amazon_2page(self):
        template = load_style_template("amazon_2page")
        assert "PR/FAQ" in template["name"]

    def test_load_google_design(self):
        template = load_style_template("google_design")
        assert "Google" in template["name"]

    def test_load_anthropic_design(self):
        template = load_style_template("anthropic_design")
        assert "Anthropic" in template["name"]

    def test_invalid_style_raises(self):
        with pytest.raises(ValueError, match="Unknown style"):
            load_style_template("nonexistent_style")


class TestGetStyleSections:
    def test_amazon_6page_sections(self):
        sections = get_style_sections("amazon_6page")
        ids = [s["id"] for s in sections]
        assert "situation" in ids
        assert "approach" in ids
        assert "risks" in ids

    def test_sections_have_required_fields(self):
        for style in VALID_STYLES:
            sections = get_style_sections(style)
            for s in sections:
                assert "id" in s
                assert "title" in s
                assert "guidance" in s


class TestGetStyleMaxPages:
    def test_amazon_6page_default(self):
        assert get_style_max_pages("amazon_6page") == 6

    def test_amazon_2page_default(self):
        assert get_style_max_pages("amazon_2page") == 2

    def test_google_design_default(self):
        assert get_style_max_pages("google_design") == 8


class TestSummarizeStyle:
    def test_produces_readable_summary(self):
        summary = summarize_style("amazon_6page")
        assert "Amazon" in summary
        assert "sections" in summary.lower() or "Sections" in summary

    def test_unknown_style(self):
        summary = summarize_style("nonexistent")
        assert "Unknown" in summary


class TestListAvailableStyles:
    def test_lists_all_styles(self):
        styles = list_available_styles()
        assert len(styles) == 4
        assert "amazon_6page" in styles
        assert "amazon_2page" in styles
        assert "google_design" in styles
        assert "anthropic_design" in styles
