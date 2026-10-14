import { ScrollArea, Stack, Table, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useState } from "react";

import type { Sample } from "../api/client";
import { formatDate, IN_PROGRESS_COLOR } from "../materials/labels";

// "In progress" colour (as the "Being prepared" badge), light variant.
const PLACED_COLOR = `var(--mantine-color-${IN_PROGRESS_COLOR}-light-color)`;

// Room for 10 rows plus the header before the table scrolls.
const ROW_HEIGHT = 37;
const VISIBLE_ROWS = 10;

interface Props {
  /** In display order (the API returns them newest first). */
  samples: Sample[];
  selectedId: string | null;
  onSelect: (sampleId: string) => void;
  /** Positions on the current frame per sample id; placed samples are highlighted. */
  placements?: Map<string, string[]>;
}

/** Searchable table of samples; click a row to select it. */
export function SamplePicker({ samples, selectedId, onSelect, placements = new Map() }: Props) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? samples.filter((s) => `${s.name} ${s.description}`.toLowerCase().includes(needle))
    : samples;

  return (
    <Stack gap="xs">
      <TextInput
        aria-label="Search samples"
        placeholder="Search by name or description"
        leftSection={<IconSearch size={16} />}
        value={query}
        onChange={(event) => setQuery(event.currentTarget.value)}
        data-autofocus
      />
      <ScrollArea.Autosize mah={ROW_HEIGHT * (VISIBLE_ROWS + 1)} type="auto" offsetScrollbars>
        <Table stickyHeader highlightOnHover verticalSpacing={8} aria-label="Samples">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Description</Table.Th>
              <Table.Th w={110}>Created</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map((sample) => {
              const selected = sample.id === selectedId;
              const placedAt = placements.get(sample.id);
              return (
                <Table.Tr
                  key={sample.id}
                  aria-selected={selected}
                  tabIndex={0}
                  bg={selected ? "var(--mantine-primary-color-light)" : undefined}
                  style={{ cursor: "pointer" }}
                  onClick={() => onSelect(sample.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(sample.id);
                    }
                  }}
                >
                  <Table.Td fw={selected ? 600 : undefined} c={placedAt ? PLACED_COLOR : undefined}>
                    {sample.name}
                    {placedAt && ` (${placedAt.join(", ")})`}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed" lineClamp={1}>
                      {sample.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatDate(sample.created_at)}</Text>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
        {shown.length === 0 && (
          <Text size="sm" c="dimmed" ta="center" py="sm">
            No matching sample
          </Text>
        )}
      </ScrollArea.Autosize>
    </Stack>
  );
}
