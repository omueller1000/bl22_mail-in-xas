# Instrument API — guide for the BL22 control software

How the beamline control software (C#) talks to the mail-in XAS portal backend. Written for a
developer (or an AI assistant) working in the control-software code base who has **no access to
the portal's source**. The authoritative contract is the backend code
(`backend/app/instrument/routes.py`, `backend/app/data/models.py`) and requirements §6.3, §10.2
and §11.1; this guide summarises them as of portal **v2.5.0**.

---

## 1. What the control software does with the portal

The portal is where users define what to measure; the control software measures it.

1. **Read** what to measure: the queue of frames waiting in internal storage, or one frame by
   its barcode.
2. **Report progress**: move a frame `internal_storage → scheduled → loaded → internal_storage`,
   and set each measurement's status to `done` or `error`.
3. **Upload raw data**: one request per sweep, right after the sweep is measured.

The control software never processes data (normalisation, χ(k), FT are done by the portal) and
never changes anything else (owners, samples, measurement settings, storage slots).

---

## 2. Connection

| | |
|---|---|
| Base URL (production) | `http://<portal-vm-internal-host>/mail-in-xas/api` |
| Base URL (dev, for testing) | `http://<portal-vm-internal-host>/mail-in-xas/dev/api` |
| Instrument endpoints | `<base>/instrument/...` |
| Health check (no key) | `GET <base>/health` |

- The real host name is **not** in this public repository; take it from the beamline
  configuration and keep it in the control software's config, not in code.
- `/api/instrument/` is **only reachable on the internal SLAC network**, calling the portal VM
  directly. Requests through the public `www-ssrl.slac.stanford.edu` proxy get **403**.
- Dev and production have **separate databases and separate API keys**. Test against dev first.
- `GET /health` → `200 {"status": "ok", "database": "ok", "environment": "production",
  "version": "2.5.0"}`; `503` with `"database": "unreachable"` if MongoDB is down. Useful as a
  start-up connectivity check and for logging the portal version.

### Authentication

- Every `/instrument/*` request sends `Authorization: Bearer <key>`.
- Keys look like `htxas_` + 40 URL-safe characters. An Admin creates them in the portal under
  **Admin → Service clients** (create a client, e.g. "BL22 control software", then a key). The
  key is **shown once**; store it in the control software's configuration (not in source
  control).
- A client may have several active keys (rotation without downtime); each can be revoked.
- Missing, malformed, unknown or revoked key → `401 {"detail": "..."}`.
- All changes the control software makes are recorded under the client's name (frame history,
  "changed by" on measurements).

---

## 3. Conventions

- JSON in and out, `Content-Type: application/json`, UTF-8. Field names are **snake_case**.
- Enum values are lowercase strings (see §6), except edges (`K`, `L1`, `L2`, `L3`).
- Timestamps are ISO 8601 in UTC.
- IDs (`id`, `sample_id`) are 24-character hex strings (MongoDB ObjectIds) — treat as opaque
  strings.
- Barcodes in URLs are case-insensitive and trimmed (`kqz-tbw` = `KQZ-TBW`); responses use
  upper case with the dash.
- Unknown fields in request bodies are **rejected** (422), so send exactly the documented fields.
- Request bodies are limited to **12 MB** (→ `413`). A sweep is typically ~1 MB of JSON.

### Errors

| Status | Meaning | Body |
|---|---|---|
| 401 | Missing/invalid/revoked API key | `{"detail": "API key required"}` |
| 403 | Called via the public proxy (from nginx, may be HTML) | — |
| 404 | Unknown barcode / measurement | `{"detail": "Unknown barcode"}` |
| 409 | Not allowed now (state conflict, duplicate sweep) | `{"detail": "Cannot move from loaded to scheduled"}` |
| 413 | Body too large | `{"detail": "Request larger than 12 MB"}` |
| 422 | Body failed validation | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
| 5xx | Server or database problem — safe to retry later | |

Note that `detail` is a **string** for most errors but a **list** for 422. Log the raw body.

---

## 4. Endpoints

### 4.1 `GET /instrument/queue` — what is waiting to be measured

Frames that are in state `internal_storage`, **locked**, and have **at least one `pending`
measurement**, sorted by container then slot. The control software's scheduler decides the
order. Each entry has the same shape as §4.2 and lists **all** measurements of the frame
(also `done`/`error` ones) — measure only those with `status == "pending"`.

Frames whose remaining measurements are all `error` are **not** in the queue; staff decide what
happens to them.

### 4.2 `GET /instrument/frames/{barcode}` — everything about one frame

Use after scanning a barcode, or to refresh one frame. Works in any state (it is a read).

```json
{
  "barcode": "KQZ-TBW",
  "state": "internal_storage",
  "locked": true,
  "safe": true,
  "storage": { "container": 2, "slot": 7, "since": "2026-10-18T09:12:44Z" },
  "owner": "Jane Doe",
  "plates": { "left": "8-circle", "right": "8-slot" },
  "positions": [
    {
      "position": "Left-A",
      "plate_type": "8-circle",
      "sample_id": "6712a0c1e4b0a1b2c3d4e5f6",
      "sample_name": "Fe2O3 reference",
      "measurements": [
        {
          "id": "6712a1f9e4b0a1b2c3d4e5f7",
          "number": 1,
          "technique": "exafs",
          "element": "Fe",
          "edge": "K",
          "detection": "transmission_sdd",
          "beam": "unfocused",
          "status": "pending",
          "error_message": null,
          "last_batch": null,
          "last_sweep": null
        }
      ]
    }
  ]
}
```

- `storage` is `null` when the frame is not in a slot; `owner` is `null` for unissued frames.
- `position` is `<Side>-<Label>`: Side ∈ `Left`, `Right`; Label `A`–`H` (8-position plates) or
  `A`–`F` (6-Circle-Gas plate, Left only). Positions without a sample are not listed.
- **A sample is located by `plate_type` + `position`**, not by the position alone: 8-Circle and
  8-Slot plates both have labels A–H, at different places.
- `plates`: the plate type mounted on each side (`null` = empty side), including plates that
  carry no samples. Each position's `plate_type` equals `plates[side]`. Plates cannot change
  once the frame is declared safe, so they are fixed for every frame the instrument sees in the
  queue.

  | Plate type id | Positions | Sides | Note |
  |---|---|---|---|
  | `8-circle` | A–H | left or right | |
  | `8-slot` | A–H | left or right | |
  | `6-circle-gas` | A–F | left only | spans the whole frame; `right` is then `null` |

  Ids are stable; new plate types may be added later (treat an unknown id as "cannot measure").
- Measurements are sorted by `number` (1, 2, … per position).
- `last_batch` / `last_sweep`: highest batch and sweep number already uploaded for this
  measurement, `null` before the first upload (see §5).
- `sample_name` is `"(deleted sample)"` in the rare case the sample record is gone.
- What to measure is defined only by `technique`, `element`, `edge`, `detection`, `beam`. The
  edge energy E0 is **not** in this response; the control software uses its own table (the
  portal uses the X-Ray Data Booklet values). The number of sweeps is decided by the control
  software.

### 4.3 `GET /instrument/storage/internal` — slot overview

All frames occupying an internal-storage slot (including `scheduled` and `loaded` ones, which
keep their slot), sorted by container, slot:

```json
[ { "barcode": "KQZ-TBW", "container": 2, "slot": 7, "state": "internal_storage", "locked": true } ]
```

### 4.4 `POST /instrument/frames/{barcode}/state` — move a frame

Body: `{"state": "scheduled"}` — one of `scheduled`, `loaded`, `internal_storage`.

Allowed moves (everything else → **409**):

| From | To | Meaning |
|---|---|---|
| `internal_storage` | `scheduled` | Scheduler picked the frame. Frame must be **locked** (else 409). |
| `scheduled` | `loaded` | Frame is in the measurement position. |
| `scheduled` | `internal_storage` | Scheduler dropped it before loading. |
| `loaded` | `internal_storage` | Measuring finished (or aborted); frame is back in its slot. |

- Returns the updated frame (same shape as §4.2).
- The frame keeps its container/slot throughout.
- 409 `"The frame changed; please reload"` if someone else changed it at the same moment.
- If the control software crashes with a frame `scheduled`/`loaded`, an operator puts the frame
  back by hand and **releases** it in the portal (→ `internal_storage`) before the software is
  restarted. So on start-up, don't assume the portal still shows your last state — re-read it.

### 4.5 `PUT /instrument/measurements/{id}/status` — report a result

Body:

```json
{ "status": "done" }
{ "status": "error", "error_message": "Edge step too small; sample too thin" }
{ "status": "pending" }
```

- `error_message` (≤ 2000 characters) is stored only with `error`; it is shown to staff and
  the user, so make it human-readable.
- `pending` again = **re-measure** (the next upload starts a new batch, §5).
- Returns the updated measurement (same shape as in §4.2, with fresh `last_batch`/`last_sweep`).
- The frame state is not checked — status can be set at any time.
- **Upload the sweeps first, then set `done`.** When the last measurement of a frame becomes
  `done` *and* every measurement of the frame has data, the portal emails the user and staff
  that the frame is complete. Setting `done` before the data is there skips that email.

### 4.6 `POST /instrument/measurements/{id}/sweeps` — upload one raw sweep

Body:

```json
{
  "batch_no": 1,
  "sweep_no": 1,
  "metadata": {
    "technique": "exafs", "element": "Fe", "edge": "K",
    "detection": "transmission_sdd", "beam": "unfocused",
    "encoder_calibration": { "...": "..." },
    "crystal_d_spacing_A": 3.1356,
    "adc_to_volt": { "...": "..." },
    "sdd_rois": [ { "roi": 1, "bin_start": 512, "bin_width": 40 } ]
  },
  "channels": [
    { "name": "energy",  "unit": "eV",       "values": [7012.0, 7012.5, 7013.0] },
    { "name": "encoder", "unit": "counts",   "values": [123456, 123401, 123346] },
    { "name": "i0",      "unit": "V",        "values": [1.21, 1.22, 1.22] },
    { "name": "i1",      "unit": "V",        "values": [0.43, 0.43, 0.42] },
    { "name": "i2",      "unit": "V",        "values": [0.18, 0.18, 0.18] },
    { "name": "fy",      "unit": "V",        "values": [0.002, 0.002, 0.002] },
    { "name": "roi1_1",  "unit": "counts/s", "values": [1500, 1510, 1490] },
    { "name": "OCR_1",   "unit": "counts/s", "values": [50000, 50100, 49900] },
    { "name": "LiveTime_1", "unit": "s",     "values": [0.98, 0.98, 0.98] }
  ]
}
```

Response **201**:

```json
{
  "id": "...", "measurement_id": "...", "frame": "KQZ-TBW", "position": "Left-A", "number": 1,
  "batch_no": 1, "sweep_no": 1,
  "measured": { "technique": "exafs", "element": "Fe", "edge": "K",
                "detection": "transmission_sdd", "beam": "unfocused" },
  "points": 3,
  "channels": ["energy", "encoder", "i0", "i1", "i2", "fy", "roi1_1", "OCR_1", "LiveTime_1"],
  "spectra": ["sample_trans", "ref_trans", "fy_norm", "sdd_roi1"],
  "uploaded_at": "2026-10-18T10:02:13Z"
}
```

Validation (→ 422):

- `batch_no`, `sweep_no`: integers 1–999.
- `channels`: 1–200 entries; names unique, 1–40 characters of `[A-Za-z0-9_]` (case-sensitive);
  `unit` ≤ 20 characters (may be empty); `values` non-empty numbers; **all channels the same
  length**; an **`energy`** channel (eV) is required.
- `metadata`: any JSON object (free-form, stored as is). Put in at least what was actually
  measured, encoder calibration, crystal lattice spacing, ADC-to-voltage calibration, and the
  SDD ROI bin start and width per ROI (integers).
- Numbers must be finite: **no NaN or Infinity** (not valid JSON).

Expected channels (the set is not fixed; the portal stores whatever is sent):

| Channel | Unit | Present |
|---|---|---|
| `energy` | eV | always |
| `encoder` | counts | always |
| `i0`, `i1`, `i2` | V | always |
| `fy` | V | always (PIPS photodiode) |
| `roi1_n`, `roi2_n` | counts/s | with SDD; n = detector element (1, 2, …) |
| `OCR_n` | counts/s | with SDD |
| `LiveTime_n` | s | with SDD |

Send all analog channels even when they carry no useful signal. **The names matter**: the data
viewer derives spectra from them — `ln(i0/i1)` needs `i0`,`i1`; `ln(i1/i2)` needs `i1`,`i2`;
`fy/i0` needs `fy`,`i0`; Σ`roi1_n`/`i0` needs `i0` and at least one `roi1_<n>` (same for
`roi2`). SDD data must already be **dead-time corrected**.

The portal takes frame, position, sample, owner and the measurement settings from its own
database at upload time, never from the upload. Raw data is **immutable** — there is no update
or delete.

---

## 5. Batch and sweep numbering

- A **batch** is one run of a measurement (N sweeps); the control software chooses N and may
  use different N per batch.
- First run: batch 1, sweeps 1…N.
- Re-measure (status set back to `pending`, by the API): next batch = `last_batch + 1`, sweeps
  continue at `last_sweep + 1`. Example: batch 1 had sweeps 1–3 → batch 2 uses 4, 5, ….
- A `sweep_no` exists **once per measurement**, across batches. Uploading an existing one →
  **409** `"Sweep 4 already exists for this measurement"`.
- That makes retries safe: if an upload times out and you don't know whether it arrived, resend
  it; a 409 means it is already stored — treat it as success.
- Read `last_batch`/`last_sweep` fresh (from §4.1/§4.2) before starting a measurement rather
  than keeping counters in the control software.

---

## 6. Enum values

| Field | Values |
|---|---|
| `technique` | `xanes`, `exafs` |
| `edge` | `K`, `L1`, `L2`, `L3` |
| `detection` | `transmission`, `transmission_tfy`, `transmission_sdd` |
| `beam` | `unfocused`, `focused` |
| measurement `status` | `pending`, `done`, `error` |
| `element` | chemical symbol, `Ti` (Z 22) … `Bi` (Z 83), limited to edges within the beamline range (default 4.7–33 keV) |
| frame `state` | `reserved`, `issued`, `shipped_to_user`, `received`, `received_on_hold`, `external_storage`, `internal_storage`, `scheduled`, `loaded`, `returning_to_user`, `returned`, `void` |

Only `internal_storage`, `scheduled`, `loaded` matter to the control software. New values may
be added in later portal versions — **don't fail on unknown enum values** when reading; log and
skip.

---

## 7. Recommended loop

```
on start-up:
    GET /health                          -> log version; stop if unreachable
    GET /instrument/storage/internal     -> find frames left scheduled/loaded by a crash;
                                            reconcile with the hardware (or ask the operator)
loop:
    GET /instrument/queue                -> pick a frame (scheduler's choice)
    POST frames/{bc}/state  scheduled
    (robot moves frame)
    POST frames/{bc}/state  loaded
    for each position, for each measurement with status == "pending":
        batch = (last_batch ?? 0) + 1;  sweep = last_sweep ?? 0
        for each sweep measured:
            sweep += 1
            POST measurements/{id}/sweeps {batch_no: batch, sweep_no: sweep, ...}
              (retry on network error/5xx; 409 duplicate = already stored)
        PUT measurements/{id}/status  done      | or  error + message
    (robot returns frame)
    POST frames/{bc}/state  internal_storage
```

- Re-read the frame (§4.2) right before measuring it: things may have changed since the queue
  was read.
- If a sweep upload keeps failing, keep the data locally and upload later; don't set `done`
  until every sweep is stored.

---

## 8. Barcode check letter (optional, for scanners/typed input)

New barcodes are `ABC-DEF`: five letters plus a check letter (Luhn mod 26). Old barcodes
`ABCD-EFGH` (eight letters, no check) stay valid. The portal checks both; checking locally just
catches typos before a request.

Algorithm: A=0 … Z=25. Going from the **rightmost** of the five letters leftwards, double every
other value starting with the rightmost; replace each doubled value v by ⌊v/26⌋ + v mod 26;
sum all values; check = (26 − sum mod 26) mod 26.

Test vector: `KQZTB` → check `W` → barcode `KQZ-TBW`.

---

## 9. Testing

- Use the **dev** base URL and a dev API key (created on the dev portal's Admin → Service
  clients).
- To get a frame into the queue on dev: as a user, create samples and measurements on a frame,
  declare safety and lock it; as an operator, scan it in (`received`) and move it to internal
  storage. Then it shows up in `GET /instrument/queue`.
- Uploaded sweeps appear in the portal's data viewer for that sample, where the derived spectra
  and processing can be checked.
- The full machine-readable schema (all endpoints, including the instrument ones) can be
  generated from the backend: `uv run python -m app.export_openapi > openapi.json` (paths
  relative to `/mail-in-xas/api`). It can feed a client generator (e.g. NSwag), though a small
  hand-written client is simpler for six endpoints.
