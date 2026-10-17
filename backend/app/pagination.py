"""Server-side pagination for the staff lists (All Frames, All Users, Material Requests).

An endpoint takes `page`, `page_size`, an optional search text `q`, its own filters and a
sort key, and returns one page of items plus the total number of matches.
"""

import re
from typing import Annotated, Any, Literal

from fastapi import Query
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection

MAX_PAGE_SIZE = 200

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Search = Annotated[str | None, Query(max_length=100)]
SortOrder = Literal["asc", "desc"]


class Page[T](BaseModel):
    items: list[T]
    # Matches in total (all pages).
    total: int
    page: int
    page_size: int


def contains(text: str) -> dict[str, str]:
    """Case-insensitive substring match (not indexed; use on small or pre-filtered sets)."""
    return {"$regex": re.escape(text), "$options": "i"}


def starts_with(text: str) -> dict[str, str]:
    """Case-sensitive prefix match, which can use an index."""
    return {"$regex": f"^{re.escape(text)}"}


def search_text(q: str | None) -> str | None:
    text = (q or "").strip()
    return text or None


async def find_page(
    collection: AsyncCollection[dict[str, Any]],
    query: dict[str, Any],
    *,
    sort: str,
    order: SortOrder,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    """One page of documents (sorted, with `_id` breaking ties) and the number of matches."""
    direction = ASCENDING if order == "asc" else DESCENDING
    keys = [(sort, direction)] if sort == "_id" else [(sort, direction), ("_id", direction)]
    total = await collection.count_documents(query)
    docs = (
        await collection.find(query)
        .sort(keys)
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )
    return docs, total
