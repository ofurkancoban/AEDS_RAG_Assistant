"""Section-aware chunking for PDFs, with a context header on every chunk.

PDF text used to be split per page into fixed-size pieces, so a chunk could
start mid-paragraph with nothing saying what it is about. Two answers went
wrong because of exactly that:

- the examination regulations' passage on seminar papers starts "The text
  should be between 30,000 and 45,000 characters", and the model gave it as
  the length of the Master's thesis;
- the module handbook continues a module over several pages, and the later
  pages (class types, contact hours, which programmes may use the module)
  never repeat the module's name.

Here a PDF's pages are joined, the running header and page numbers that
repeat on every page are dropped, the text is split at its headings
("Section 5" + its title, "Appendix 1: ...", a module line such as
"wir874 - Advanced Microeconomics"), each section is split into chunks that
never cross into the next section, and every chunk starts with
"[<document title> | <section heading>]". The header is part of the text
that is embedded, matched by BM25 and shown to the model.
"""

import re
from collections import Counter

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# "Section 5" on a line of its own; the title follows on the next line.
_SECTION_NUMBER_ONLY = re.compile(r"^(?:Section|§)\s*\d+[a-z]?$")
# "Section 5 Examination components" on one line. The title must start with a
# capital: a sentence that merely begins with a reference ("Section 13 and
# not previously involved ...") is prose, not a heading.
_SECTION_WITH_TITLE = re.compile(r"^(?:Section|§)\s*\d+[a-z]?\s+[A-ZÄÖÜ][^.]{2,90}$")
_APPENDIX = re.compile(r"^(?:Appendix|Anlage)\s+\d+\s*[a-z]?\s*:?\s*\S.{0,100}$")
# "wir874 - Advanced Microeconomics": a module in the module handbook.
_MODULE = re.compile(r"^[a-z]{2,4}\d{3,4}[a-z]?\s+-\s+\S.{2,110}$")
_PAGE_NUMBER = re.compile(r"^\s*\d+\s*(?:/\s*\d+)?\s*$")
# A section up to this long is handed to the model whole (as parent_content,
# like the Markdown sections in ingestion/chunker.py) whichever of its chunks
# matched: a module-handbook entry's class types sat in its second chunk,
# which ranked below the first, and the answer said "lecture only". Covers
# every regulation section but the module list and nearly every module.
PARENT_MAX_CHARS = 5000
# Table-of-contents lines end in dot leaders and a page number.
_DOT_LEADER = re.compile(r"\.{4,}")


def _repeated_lines(pages: list[str]) -> set[str]:
    """Lines printed on most pages (running header, footer): noise in every
    chunk, and they would otherwise be the first thing each page says."""
    if len(pages) < 3:
        return set()
    counts = Counter(line.strip() for page in pages for line in set(page.splitlines()) if line.strip())
    return {line for line, count in counts.items() if count >= len(pages) / 2}


def _heading_at(lines: list[str], i: int) -> tuple[str, int] | None:
    """The heading starting at lines[i] and how many lines it spans."""
    line = lines[i].strip()
    if not line or _DOT_LEADER.search(line):
        return None
    if _SECTION_NUMBER_ONLY.match(line):
        title = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if title and title[0].isupper() and len(title) <= 100 and not _DOT_LEADER.search(title):
            return f"{line} {title}", 2
        return line, 1
    if _SECTION_WITH_TITLE.match(line) or _APPENDIX.match(line) or _MODULE.match(line):
        return line, 1
    return None


def split_sections(pages: list[tuple[int, str]]) -> list[dict]:
    """[(page_number, text)] -> [{"heading", "text", "page"}] in reading order.
    Text before the first heading is a section with an empty heading."""
    noise = _repeated_lines([text for _, text in pages])
    lines: list[tuple[int, str]] = []
    for page_number, text in pages:
        for line in text.splitlines():
            stripped = line.strip()
            # Table-of-contents lines name every module and section, so they
            # match almost any question while answering none.
            if stripped in noise or _PAGE_NUMBER.match(stripped) or _DOT_LEADER.search(stripped):
                continue
            lines.append((page_number, line))

    texts = [line for _, line in lines]
    sections: list[dict] = []
    current = {"heading": "", "lines": [], "page": lines[0][0] if lines else 1}
    i = 0
    while i < len(lines):
        found = _heading_at(texts, i)
        if found:
            heading, span = found
            sections.append(current)
            current = {"heading": heading, "lines": [], "page": lines[i][0]}
            i += span
            continue
        current["lines"].append(texts[i])
        i += 1
    sections.append(current)

    result = []
    for section in sections:
        body = "\n".join(section["lines"]).strip()
        # A heading with nothing under it is a table-of-contents entry.
        if len(re.sub(r"\s", "", body)) < 30:
            continue
        result.append({"heading": section["heading"], "text": body, "page": section["page"]})
    return result


def chunk_pdf(
    documents: list[Document], title: str, chunk_size: int, chunk_overlap: int
) -> list[Document]:
    """Page documents of one PDF -> chunks headed "[title | section]"."""
    if not documents:
        return []
    base_metadata = {k: v for k, v in documents[0].metadata.items() if k != "page"}
    pages = sorted((doc.metadata.get("page", 1), doc.page_content) for doc in documents)
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks = []
    for section in split_sections(pages):
        header = f"[{title} | {section['heading']}]" if section["heading"] else f"[{title}]"
        pieces = splitter.split_text(section["text"])
        whole = f"{header}\n{section['text']}"
        for piece in pieces:
            metadata = {**base_metadata, "page": section["page"], "section": section["heading"]}
            if len(pieces) > 1 and len(whole) <= PARENT_MAX_CHARS:
                metadata["parent_content"] = whole
            chunks.append(Document(page_content=f"{header}\n{piece}", metadata=metadata))
    return chunks
