from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langgraph.graph.message import add_messages


class RagState(TypedDict):
    messages: Annotated[list, add_messages]
    retrieved_docs: list[Document]
    source_id_filter: str | None
    detected_contribution: dict | None
    direct_answer: str | None
    current_semester_number: int | None
    awaiting_semester_number: bool
    node_latencies: dict[str, float]
    # Set when the answer embeds a value derived from today's date (e.g. the
    # "N days left until the deadline" countdown), which makes it correct only
    # on the day it was produced - the answer cache must not replay it later.
    time_sensitive: bool
