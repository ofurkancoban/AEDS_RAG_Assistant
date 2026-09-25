import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from config import settings
from db.chroma_client import add_chunks, delete_chunks_by_source_id
from ingestion.topics import classify_topics

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".pptx", ".html", ".htm", ".csv"}

SOURCES_MANIFEST = "sources.json"


@lru_cache(maxsize=1)
def _load_source_manifest() -> dict:
    """Parse data/documents/sources.json into filename -> {url, valid_until}.

    Each entry may be either a bare URL string (the original format) or an
    object with "url" plus optional freshness metadata, so existing entries
    keep working untouched and only genuinely time-bounded documents need the
    longer form.
    """
    manifest_path = settings.documents_dir / SOURCES_MANIFEST
    if not manifest_path.exists():
        return {}

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    parsed = {}
    for filename, value in raw.items():
        if isinstance(value, str):
            parsed[filename] = {"url": value, "valid_until": None}
        else:
            valid_until = value.get("valid_until")
            parsed[filename] = {
                "url": value.get("url"),
                "valid_until": (
                    datetime.strptime(valid_until, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if valid_until
                    else None
                ),
            }
    return parsed


def _load_source_urls() -> dict:
    return {name: meta["url"] for name, meta in _load_source_manifest().items() if meta["url"]}


def load_source_urls() -> dict[str, str]:
    """Public wrapper for scripts/source_refresh.py - filename -> source URL,
    skipping entries with no URL (hand-authored files like catalog.csv)."""
    return _load_source_urls()


_MARKDOWN_HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2"), ("###", "h3")]
# Deliberately smaller than settings.chunk_size: these are the "child" chunks
# used for embedding/BM25 matching once a header-bounded section is still too
# long to embed as one chunk - see _chunk_markdown's docstring.
_CHILD_CHUNK_SIZE = 400
_CHILD_CHUNK_OVERLAP = 50


def _chunk_markdown(documents: list[Document]) -> list[Document]:
    """Splits markdown documents along their header hierarchy (#, ##, ###)
    first, so a chunk never silently crosses into an unrelated section - a
    generic multi-topic page's boilerplate has previously bled into an
    unrelated answer, and a routing heuristic tuned for one section's wording
    has misfired by matching a different section entirely, both because nothing
    enforced a section boundary at chunk time.

    Parent/child split: if a header-bounded section is still longer than
    chunk_size, it's further split into smaller 'child' pieces for more
    precise embedding/BM25 matching, but each child's metadata carries the
    FULL section text as parent_content - generate_node substitutes this in
    when building the LLM's context, so a match on a small, precise child
    chunk still hands the model the section's full surrounding context rather
    than a fragment cut off mid-thought."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_MARKDOWN_HEADERS_TO_SPLIT_ON, strip_headers=False
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHILD_CHUNK_SIZE, chunk_overlap=_CHILD_CHUNK_OVERLAP
    )

    chunks = []
    for document in documents:
        try:
            sections = header_splitter.split_text(document.page_content)
        except Exception:
            # No headers found (or a malformed one) - fall back to treating
            # the whole document as a single section rather than dropping it.
            sections = [document]

        for section in sections:
            parent_text = section.page_content
            if not parent_text.strip():
                continue
            if len(parent_text) <= settings.chunk_size:
                chunks.append(Document(page_content=parent_text, metadata=dict(document.metadata)))
            else:
                for child_text in child_splitter.split_text(parent_text):
                    chunks.append(
                        Document(
                            page_content=child_text,
                            metadata={**document.metadata, "parent_content": parent_text},
                        )
                    )
    return chunks


def chunk_documents(
    documents: list[Document],
    source_id: str,
    source_url: str | None = None,
    is_markdown: bool = False,
) -> list[Document]:
    # Table documents (from load_pdf's pdfplumber pass) are kept whole - splitting
    # a markdown table mid-row would scramble which value belongs to which
    # column, defeating the point of extracting it as a table in the first place.
    table_docs = [doc for doc in documents if doc.metadata.get("is_table")]
    text_docs = [doc for doc in documents if not doc.metadata.get("is_table")]

    if is_markdown:
        chunks = _chunk_markdown(text_docs) + table_docs
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        chunks = splitter.split_documents(text_docs) + table_docs

    for chunk in chunks:
        chunk.metadata["source_id"] = source_id
        chunk.metadata["status"] = "approved"
        if source_url:
            chunk.metadata["source_url"] = source_url
        topics = classify_topics(chunk.page_content)
        chunk.metadata["primary_topic"] = topics[0]
        chunk.metadata["topics"] = ",".join(topics)
    return chunks


def ingest_file(path: Path, source_id: str | None = None) -> int:
    """Ingest an admin-uploaded document directly as approved chunks."""
    from ingestion.loaders import load_document

    source_id = source_id or path.stem
    source_url = _load_source_urls().get(path.name)
    documents = load_document(path)
    chunks = chunk_documents(documents, source_id, source_url, is_markdown=path.suffix.lower() == ".md")

    texts = [chunk.page_content for chunk in chunks]
    metadatas = [chunk.metadata for chunk in chunks]
    ids = [str(uuid.uuid4()) for _ in chunks]

    add_chunks(texts=texts, metadatas=metadatas, ids=ids)
    return len(chunks)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ingest_and_record_file(path: Path, session) -> int | None:
    """Ingest a file and record it in IngestedDocument so it is not re-embedded
    on a later startup scan. Returns the chunk count, or None if the file's
    content hash matches what's already recorded (skipped as unchanged)."""
    from db.models import IngestedDocument
    from ingestion.structured_sync import sync_structured_data

    # Runs unconditionally (not gated by the hash-change check below) so the
    # SQL tables get (re-)populated even on a restart where Chroma chunking
    # itself is skipped as unchanged - cheap for the two known structured
    # files (a no-op for everything else) and keeps the relational side always
    # in sync with the source file rather than depending on Chroma's own
    # re-ingestion state.
    sync_structured_data(path)

    file_hash = _file_hash(path)
    valid_until = _load_source_manifest().get(path.name, {}).get("valid_until")
    existing = session.query(IngestedDocument).filter(IngestedDocument.filename == path.name).first()
    if existing is not None and existing.file_hash == file_hash:
        # Freshness metadata lives in the manifest, not in the file, so it can
        # change while the file's own content hash stays identical - syncing it
        # before the unchanged-file early return is what makes editing
        # sources.json alone take effect on the next startup.
        if existing.valid_until != valid_until:
            existing.valid_until = valid_until
            session.commit()
        return None

    if existing is not None:
        # file changed since last ingest - drop its old chunks first so stale
        # and updated content don't both end up in the vector store
        delete_chunks_by_source_id(path.stem)

    chunk_count = ingest_file(path)

    if existing is not None:
        existing.file_hash = file_hash
        existing.chunk_count = chunk_count
        existing.valid_until = valid_until
    else:
        session.add(
            IngestedDocument(
                filename=path.name,
                file_hash=file_hash,
                chunk_count=chunk_count,
                valid_until=valid_until,
            )
        )
    session.commit()
    return chunk_count


def scan_and_ingest_documents_folder() -> None:
    """Scan settings.documents_dir for new or changed files and embed them as
    approved chunks. Called on backend startup so dropping PDFs into the folder
    is enough to have them learned, without going through the admin upload API."""
    from db.models import SessionLocal

    session = SessionLocal()
    try:
        for path in sorted(settings.documents_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            chunk_count = ingest_and_record_file(path, session)
            if chunk_count is not None:
                logger.info("Ingested %s (%d chunks)", path.name, chunk_count)
    finally:
        session.close()


def delete_ingested_document(filename: str, session) -> bool:
    """Reverses ingest_and_record_file: drops the file's chunks from Chroma,
    removes it from disk, and forgets its IngestedDocument record so it would
    be re-ingested from scratch if re-added later. Returns False if no such
    file was ever recorded (nothing to delete)."""
    from db.models import IngestedDocument

    existing = session.query(IngestedDocument).filter(IngestedDocument.filename == filename).first()
    if existing is None:
        return False

    delete_chunks_by_source_id(Path(filename).stem)

    path = settings.documents_dir / filename
    if path.exists():
        path.unlink()

    session.delete(existing)
    session.commit()
    return True


def ingest_approved_submission(content: str, source_id: str, submission_id: int) -> str:
    """Embed a single admin-approved user submission (new_info or correction) as one chunk."""
    chunk_id = str(uuid.uuid4())
    topics = classify_topics(content)
    add_chunks(
        texts=[content],
        metadatas=[
            {
                "source_id": source_id,
                "status": "approved",
                "origin": "user_submission",
                "submission_id": submission_id,
                "primary_topic": topics[0],
                "topics": ",".join(topics),
            }
        ],
        ids=[chunk_id],
    )
    return chunk_id
