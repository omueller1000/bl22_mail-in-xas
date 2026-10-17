import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";

export type SortOrder = "asc" | "desc";

export const PAGE_SIZES = [25, 50, 100];

// Wait this long after the last keystroke before searching on the server.
const SEARCH_DELAY_MS = 300;

/** Page, page size, sort and search of a server-paged list (see PagedTable). */
export function usePaging<S extends string>(defaults: { sort: S; order: SortOrder }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sort, setSort] = useState<S>(defaults.sort);
  const [order, setOrder] = useState<SortOrder>(defaults.order);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), SEARCH_DELAY_MS);

  return {
    page,
    pageSize,
    sort,
    order,
    search,
    setPage,
    setPageSize: (size: number) => {
      setPageSize(size);
      setPage(1);
    },
    setSearch: (text: string) => {
      setSearch(text);
      setPage(1);
    },
    /** Click on a column header: sort by it, or reverse the order if it already is. */
    toggleSort: (key: S) => {
      if (key === sort) {
        setOrder(order === "asc" ? "desc" : "asc");
      } else {
        setSort(key);
        setOrder("asc");
      }
      setPage(1);
    },
    /** Call when a filter changes, so the list starts again at page 1. */
    firstPage: () => setPage(1),
    /** Query parameters for the API. */
    params: {
      page,
      page_size: pageSize,
      sort,
      order,
      q: debouncedSearch || undefined,
    },
  };
}

export type Paging<S extends string> = ReturnType<typeof usePaging<S>>;
