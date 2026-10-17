import {
  Alert,
  Group,
  Pagination,
  Select,
  Table,
  type TableThProps,
  Text,
  UnstyledButton,
} from "@mantine/core";
import { IconChevronDown, IconChevronUp, IconSelector } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { PageLoader } from "../auth/guards";
import { PAGE_SIZES, type Paging } from "./paging";

export interface PagedColumn<T, S extends string> {
  key: string;
  label: ReactNode;
  /** Sort key sent to the API; the header becomes a sort button. */
  sort?: S;
  render: (row: T) => ReactNode;
  th?: TableThProps;
}

interface PageData<T> {
  items: T[];
  total: number;
}

interface Props<T, S extends string> {
  columns: PagedColumn<T, S>[];
  paging: Paging<S>;
  query: { data?: PageData<T>; isPending: boolean; isFetching: boolean; error: Error | null };
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  minWidth?: number;
  empty?: string;
}

/** A table whose rows the server pages, sorts and searches (see usePaging). */
export function PagedTable<T, S extends string>({
  columns,
  paging,
  query,
  rowKey,
  onRowClick,
  minWidth = 800,
  empty = "Nothing found.",
}: Props<T, S>) {
  const { data, isPending, isFetching, error } = query;
  if (isPending) return <PageLoader />;
  if (error) return <Alert color="red">{error.message}</Alert>;
  if (!data) return null;

  const pages = Math.max(1, Math.ceil(data.total / paging.pageSize));
  const first = (paging.page - 1) * paging.pageSize + 1;
  const last = first + data.items.length - 1;

  return (
    <>
      {data.items.length === 0 ? (
        <Text c="dimmed">{data.total > 0 ? "No rows on this page." : empty}</Text>
      ) : (
        <Table.ScrollContainer minWidth={minWidth}>
          <Table
            striped
            highlightOnHover
            // Previous page stays visible, dimmed, while the next one loads.
            style={{ opacity: isFetching ? 0.6 : 1, transition: "opacity 150ms" }}
          >
            <Table.Thead>
              <Table.Tr>
                {columns.map((column) => (
                  <Table.Th
                    key={column.key}
                    aria-sort={
                      column.sort && column.sort === paging.sort
                        ? paging.order === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                    {...column.th}
                  >
                    {column.sort ? (
                      <SortButton column={column} paging={paging} />
                    ) : (
                      column.label
                    )}
                  </Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.items.map((row) => (
                <Table.Tr
                  key={rowKey(row)}
                  style={onRowClick ? { cursor: "pointer" } : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((column) => (
                    <Table.Td key={column.key}>{column.render(row)}</Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {data.items.length > 0
            ? `${first.toLocaleString()}–${last.toLocaleString()} of ${data.total.toLocaleString()}`
            : `${data.total.toLocaleString()} in total`}
        </Text>
        <Group gap="sm">
          <Pagination
            total={pages}
            value={Math.min(paging.page, pages)}
            onChange={paging.setPage}
            size="sm"
            withEdges
            getControlProps={(control) => ({ "aria-label": `${control} page` })}
          />
          <Select
            aria-label="Rows per page"
            data={PAGE_SIZES.map((size) => ({ value: String(size), label: `${size} / page` }))}
            value={String(paging.pageSize)}
            onChange={(value) => value && paging.setPageSize(Number(value))}
            allowDeselect={false}
            size="xs"
            w={110}
          />
        </Group>
      </Group>
    </>
  );
}

function SortButton<T, S extends string>({
  column,
  paging,
}: {
  column: PagedColumn<T, S>;
  paging: Paging<S>;
}) {
  const active = paging.sort === column.sort;
  const Icon = !active ? IconSelector : paging.order === "asc" ? IconChevronUp : IconChevronDown;
  return (
    <UnstyledButton
      onClick={() => paging.toggleSort(column.sort!)}
      aria-label={`Sort by ${typeof column.label === "string" ? column.label : column.key}`}
      fw={700}
      fz="sm"
    >
      <Group gap={4} wrap="nowrap">
        {column.label}
        <Icon size={14} />
      </Group>
    </UnstyledButton>
  );
}
