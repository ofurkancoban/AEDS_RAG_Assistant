"""PDF chunks never cross a section and always say which document and
section they come from."""

from langchain_core.documents import Document

from ingestion.pdf_sections import chunk_pdf, split_sections

REGULATIONS = [
    (1, "Examination regulations\nTable of contents\n5 Examination components ..... 4\n"
        "Examination regulations - running header\n1 / 3"),
    (2, "Examination regulations - running header\nSection 5\nExamination components\n"
        "(3) A seminar paper is written work.\nThe text should be between 30,000 and 45,000 characters long.\n2 / 3"),
    (3, "Examination regulations - running header\nSection 10\nFinal Master's module\n"
        "The Master's thesis should not exceed 200,000 characters, as required by\n"
        "Section 13 and not previously involved is prose, not a heading.\n3 / 3"),
]


def _docs(pages):
    return [Document(page_content=text, metadata={"source_file": "x.pdf", "page": n}) for n, text in pages]


def test_sections_follow_the_headings_and_drop_page_noise():
    sections = split_sections(REGULATIONS)
    headings = [s["heading"] for s in sections]
    assert "Section 5 Examination components" in headings
    assert "Section 10 Final Master's module" in headings
    seminar = next(s for s in sections if s["heading"].startswith("Section 5"))
    assert "45,000" in seminar["text"] and "200,000" not in seminar["text"]
    assert all("running header" not in s["text"] for s in sections)
    assert all("2 / 3" not in s["text"] for s in sections)


def test_a_sentence_starting_with_a_section_reference_is_not_a_heading():
    sections = split_sections(REGULATIONS)
    assert not any(s["heading"].startswith("Section 13") for s in sections)


def test_every_chunk_carries_document_and_section():
    chunks = chunk_pdf(_docs(REGULATIONS), "Examination regulations 2026", chunk_size=1500, chunk_overlap=200)
    seminar = next(c for c in chunks if "45,000" in c.page_content)
    assert seminar.page_content.startswith("[Examination regulations 2026 | Section 5 Examination components]")
    assert seminar.metadata["page"] == 2


def test_module_handbook_continuation_pages_keep_their_module():
    pages = [
        (1, "Module handbook header\nwir874 - Advanced Microeconomics ........ 10\n1 / 3"),
        (2, "Module handbook header\nwir874 - Advanced Microeconomics\nModule label Advanced Microeconomics\n"
            "Credit points 6.0 KP\n2 / 3"),
        (3, "Module handbook header\nCourse or seminar 4 WiSe 56 h\nModule Capacity : unrestricted\n3 / 3"),
    ]
    chunks = chunk_pdf(_docs(pages), "Module handbook", chunk_size=1500, chunk_overlap=200)
    capacity = next(c for c in chunks if "Module Capacity" in c.page_content)
    assert capacity.page_content.startswith("[Module handbook | wir874 - Advanced Microeconomics]")
    assert all("........" not in c.page_content for c in chunks)
