import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  FileButton,
  Group,
  Menu,
  Modal,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconDots, IconFileTypePdf, IconLock } from "@tabler/icons-react";
import { useState } from "react";

import type { Sample } from "../api/client";
import {
  MSDS_MAX_BYTES,
  msdsUrl,
  useCreateSample,
  useDeleteMsds,
  useDeleteSample,
  useSamples,
  useSetArchived,
  useUpdateSample,
  useUploadMsds,
} from "../api/samples";
import { PageLoader } from "../auth/guards";
import { formatDate } from "../materials/labels";

/** The user's sample library (requirements §8.2). */
export function SamplesPage() {
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Sample | "new" | null>(null);
  const { data: samples, isPending, error } = useSamples(showArchived);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Samples</Title>
        <Button onClick={() => setEditing("new")}>New sample</Button>
      </Group>
      <Text c="dimmed" size="sm">
        Define each material once and place it on as many frame positions as you like. Samples
        on a frame declared safe can no longer be changed.
      </Text>
      <Switch
        label="Show archived samples"
        checked={showArchived}
        onChange={(event) => setShowArchived(event.currentTarget.checked)}
      />
      {isPending ? (
        <PageLoader />
      ) : error ? (
        <Alert color="red">{error.message}</Alert>
      ) : samples.length === 0 ? (
        <Text c="dimmed">No samples yet.</Text>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Description</Table.Th>
                <Table.Th>MSDS</Table.Th>
                <Table.Th>Frames</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th w={40} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {samples.map((sample) => (
                <SampleRow key={sample.id} sample={sample} onEdit={() => setEditing(sample)} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <SampleModal
        // Fresh form per sample
        key={editing === null ? "closed" : editing === "new" ? "new" : editing.id}
        sample={editing === "new" ? null : editing}
        opened={editing !== null}
        onClose={() => setEditing(null)}
      />
    </Stack>
  );
}

function SampleRow({ sample, onEdit }: { sample: Sample; onEdit: () => void }) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const archive = useSetArchived();
  const upload = useUploadMsds();
  const removeMsds = useDeleteMsds();
  const fail = (err: Error) => notifications.show({ color: "red", message: err.message });

  const uploadFile = (file: File | null) => {
    if (!file) return;
    if (file.size > MSDS_MAX_BYTES) return fail(new Error("The MSDS must be smaller than 1 MB"));
    upload.mutate({ id: sample.id, file }, { onError: fail });
  };

  return (
    <Table.Tr c={sample.archived ? "dimmed" : undefined}>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <Text fw={500}>{sample.name}</Text>
          {sample.frozen && (
            <Tooltip label="On a frame declared safe; can no longer be changed">
              <IconLock size={14} aria-label="frozen" />
            </Tooltip>
          )}
          {sample.archived && (
            <Badge size="xs" variant="outline" color="gray">
              archived
            </Badge>
          )}
        </Group>
      </Table.Td>
      <Table.Td maw={320}>
        <Text size="sm" lineClamp={2}>
          {sample.description}
        </Text>
      </Table.Td>
      <Table.Td>
        {sample.msds ? (
          <Anchor href={msdsUrl(sample.id)} size="sm">
            <Group gap={4} wrap="nowrap">
              <IconFileTypePdf size={16} />
              <Text size="sm" truncate maw={160}>
                {sample.msds.filename}
              </Text>
            </Group>
          </Anchor>
        ) : (
          <Text size="sm" c="dimmed">
            —
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="sm" ff="monospace">
          {sample.frames.join(", ")}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatDate(sample.created_at)}</Text>
      </Table.Td>
      <Table.Td>
        <FileButton onChange={uploadFile} accept="application/pdf">
          {(uploadProps) => (
            <Menu position="bottom-end" withinPortal>
              <Menu.Target>
                <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${sample.name}`}>
                  <IconDots size={18} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item onClick={onEdit} disabled={sample.frozen}>
                  Edit
                </Menu.Item>
                <Menu.Item {...uploadProps} disabled={sample.frozen || upload.isPending}>
                  {sample.msds ? "Replace MSDS…" : "Upload MSDS…"}
                </Menu.Item>
                {sample.msds && (
                  <Menu.Item
                    disabled={sample.frozen}
                    onClick={() => removeMsds.mutate(sample.id, { onError: fail })}
                  >
                    Remove MSDS
                  </Menu.Item>
                )}
                <Menu.Item
                  onClick={() =>
                    archive.mutate({ id: sample.id, archived: !sample.archived }, { onError: fail })
                  }
                >
                  {sample.archived ? "Unarchive" : "Archive"}
                </Menu.Item>
                <Menu.Divider />
                <Menu.Item
                  color="red"
                  disabled={!sample.deletable}
                  onClick={() => setConfirmDelete(true)}
                >
                  Delete…
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </FileButton>
        <DeleteModal sample={sample} opened={confirmDelete} onClose={() => setConfirmDelete(false)} />
      </Table.Td>
    </Table.Tr>
  );
}

function SampleModal({
  sample,
  opened,
  onClose,
}: {
  sample: Sample | null;
  opened: boolean;
  onClose: () => void;
}) {
  const create = useCreateSample();
  const update = useUpdateSample();
  const mutation = sample ? update : create;
  const form = useForm({
    initialValues: { name: sample?.name ?? "", description: sample?.description ?? "" },
    validate: { name: (value) => (value.trim() ? null : "Name is required") },
  });

  const submit = form.onSubmit((values) => {
    const body = { name: values.name.trim(), description: values.description.trim() };
    const done = { onSuccess: onClose };
    if (sample) update.mutate({ id: sample.id, ...body }, done);
    else create.mutate(body, done);
  });

  return (
    <Modal opened={opened} onClose={onClose} title={sample ? "Edit sample" : "New sample"}>
      <form onSubmit={submit}>
        <Stack>
          <TextInput label="Name" withAsterisk maxLength={200} data-autofocus {...form.getInputProps("name")} />
          <Textarea
            label="Description"
            description="Composition, preparation, anything the beamline staff should know"
            autosize
            minRows={3}
            maxLength={4000}
            {...form.getInputProps("description")}
          />
          {mutation.isError && <Alert color="red">{mutation.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {sample ? "Save" : "Create"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function DeleteModal({
  sample,
  opened,
  onClose,
}: {
  sample: Sample;
  opened: boolean;
  onClose: () => void;
}) {
  const remove = useDeleteSample();
  return (
    <Modal opened={opened} onClose={onClose} title="Delete sample">
      <Stack>
        <Text>
          Permanently delete <b>{sample.name}</b>
          {sample.frames.length > 0 && <> and remove it from frame {sample.frames.join(", ")}</>}?
          This cannot be undone.
        </Text>
        {remove.isError && <Alert color="red">{remove.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button
            color="red"
            loading={remove.isPending}
            onClick={() => remove.mutate(sample.id, { onSuccess: onClose })}
          >
            Delete
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
