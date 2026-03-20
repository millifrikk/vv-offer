"""Parser for verklýsing (work description) PDF files."""

import re
from pathlib import Path

import pdfplumber

from app.models.schemas import VerklysingSection

# Pattern to match section numbers at the start of a line: 3.0, 3.1.1, 3.5.10, etc.
SECTION_PATTERN = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\s+(.+?)$", re.MULTILINE)

# Pattern for the chapter header (e.g., "3 LAGNIR")
CHAPTER_PATTERN = re.compile(r"^(\d+)\s+([A-ZÁÐÉÍÓÚÝÞÆÖ][A-ZÁÐÉÍÓÚÝÞÆÖ\s]+)$", re.MULTILINE)


class VerklysingParser:
    """Parses verklýsing (work description) PDFs into structured sections."""

    def parse(self, file_path: str | Path) -> list[VerklysingSection]:
        full_text, page_texts = self._extract_text(file_path)
        sections = self._split_into_sections(full_text, page_texts)
        return sections

    def _extract_text(self, file_path: str | Path) -> tuple[str, list[tuple[int, str]]]:
        """Extract text from all pages. Returns (full_text, [(page_num, page_text)])."""
        page_texts = []
        all_text_parts = []

        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = self._clean_page_text(text, i + 1)

                # Skip table of contents pages (they create duplicate section entries)
                if self._is_toc_page(text):
                    page_texts.append((i + 1, text))
                    continue

                page_texts.append((i + 1, text))
                all_text_parts.append(text)

        full_text = "\n".join(all_text_parts)
        return full_text, page_texts

    def _is_toc_page(self, text: str) -> bool:
        """Detect table of contents pages by looking for many underscored section references."""
        underscore_lines = sum(1 for line in text.split("\n") if "____" in line)
        return underscore_lines > 5

    def _clean_page_text(self, text: str, page_num: int) -> str:
        """Remove headers, footers, and page numbers."""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # Skip page numbers (standalone numbers at end of page)
            if re.match(r"^\d+-\d+$", stripped):
                continue
            # Skip repeated chapter headers used as page headers
            if re.match(r"^\d+\s+[A-ZÁÐÉÍÓÚÝÞÆÖ]{3,}$", stripped):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _split_into_sections(
        self, full_text: str, page_texts: list[tuple[int, str]]
    ) -> list[VerklysingSection]:
        """Split the full text into sections based on section number patterns."""
        # Find all section starts
        section_starts = []
        for match in SECTION_PATTERN.finditer(full_text):
            section_nr = match.group(1)
            title = match.group(2).strip()
            start_pos = match.start()

            # Filter out false positives:
            # - Section numbers that don't start with a plausible chapter number
            # - Titles that look like inline text fragments (too short, start with lowercase, etc.)
            top_level = section_nr.split(".")[0]
            if not (1 <= int(top_level) <= 9):
                continue
            # Skip if title starts with special characters or looks like a fragment
            if title.startswith(("=", "(", "–", "-", "_")):
                continue
            # Skip very short titles that are likely inline references
            if len(title) < 3:
                continue

            section_starts.append((section_nr, title, start_pos))

        if not section_starts:
            return []

        # Deduplicate: if same section_nr appears multiple times, keep the one with more content
        sections = []
        seen_sections: dict[str, int] = {}  # section_nr -> index in sections list
        for i, (section_nr, title, start_pos) in enumerate(section_starts):
            # Get text until next section starts
            if i + 1 < len(section_starts):
                end_pos = section_starts[i + 1][2]
            else:
                end_pos = len(full_text)

            raw_text = full_text[start_pos:end_pos].strip()

            # Remove the section header line from the body text
            body_lines = raw_text.split("\n")[1:]
            body_text = "\n".join(body_lines).strip()

            # Find which pages this section appears on
            pages = self._find_pages_for_text(raw_text[:100], page_texts)

            # Clean the title: remove trailing underscores and page references
            clean_title = re.sub(r"\s*_+\s*\d+-\d+\s*$", "", title).strip()
            clean_title = re.sub(r"\s*_+\s*$", "", clean_title).strip()

            section = VerklysingSection(
                section_nr=section_nr,
                title=clean_title,
                raw_text=body_text,
                requirements=[],  # Will be populated by AI engine later
                page_numbers=pages,
            )

            # Deduplicate: keep the version with more content
            if section_nr in seen_sections:
                existing_idx = seen_sections[section_nr]
                if len(body_text) > len(sections[existing_idx].raw_text):
                    sections[existing_idx] = section
            else:
                seen_sections[section_nr] = len(sections)
                sections.append(section)

        return sections

    def _find_pages_for_text(
        self, text_snippet: str, page_texts: list[tuple[int, str]]
    ) -> list[int]:
        """Find which page(s) contain a text snippet."""
        pages = []
        # Use first 60 chars as a search key
        search = text_snippet[:60].strip()
        for page_num, page_text in page_texts:
            if search in page_text:
                pages.append(page_num)
        return pages

    def get_section_by_nr(
        self, sections: list[VerklysingSection], section_nr: str
    ) -> VerklysingSection | None:
        """Find a section by its number."""
        for section in sections:
            if section.section_nr == section_nr:
                return section
        return None

    def get_sections_for_parent(
        self, sections: list[VerklysingSection], parent_nr: str
    ) -> list[VerklysingSection]:
        """Get all sections that fall under a parent section number."""
        return [s for s in sections if s.section_nr.startswith(parent_nr + ".") or s.section_nr == parent_nr]
