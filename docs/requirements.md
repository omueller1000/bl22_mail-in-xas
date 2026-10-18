# Mail-in XAS Portal — Requirements

Status: **Draft v0.1** — for review before implementation.
Predecessor (reference only, not to be ported): `OliverM1000/BL22HT_UI`, `OliverM1000/BL22HT_API`.

Items marked **[Assumption]** were not explicitly decided and should be confirmed. Open questions are collected in §13.

---

## 1. Purpose and scope

A web portal for the BL22 high-throughput XAS mail-in program. It lets users:

1. manage their account and contact/shipping details,
2. request sample-mounting materials, assemble sample frames, define samples, and declare safety,
3. define XAS measurements per sample position,
4. inspect and download their data.

It lets beamline staff track frames through shipping, receiving and storage by barcode scanning, and it is the **input to the beamline's automated measurement queue**: the beamline control software reads measurement definitions from the portal's backend and uploads raw data to it; the portal processes the data itself.

**Out of scope for this version:** data sharing between users, Slack notifications, audit trail, courier tracking, packing lists/labels, imaging measurements, user deactivation, editable plate-type catalog, internal TLS.

---

## 2. Technology and architecture

| Layer | Choice |
|---|---|
| Frontend | Vite + React + TypeScript, Plotly.js for charts |
| Backend | Python + FastAPI (Pydantic models; OpenAPI spec generates TypeScript types for the frontend) |
| Database | MongoDB; only the backend accesses it |
| Web server | nginx on the application VM |

```
Browser ──HTTPS──▶ SLAC reverse proxy (TLS) ──HTTP──▶ App VM: nginx
                                                       ├─ /mail-in-xas/                 → prod frontend (static)
                                                       ├─ /mail-in-xas/api/             → prod backend (FastAPI)
                                                       ├─ /mail-in-xas/dev/             → dev frontend   ┐ denied when request
                                                       ├─ /mail-in-xas/dev/api/         → dev backend    ┘ comes via SLAC proxy
                                                       └─ */api/instrument/*            → denied (403)

Control software ──internal network──▶ App VM backend /api/instrument/*   (API key)
Backends ──internal──▶ MongoDB (databases: prod and dev, separate)
```

- Production URL (fixed): `https://www-ssrl.slac.stanford.edu/mail-in-xas/`
- The frontend talks to the backend only via the REST API (JSON over HTTP).
- Frontend and API share one origin, so no CORS configuration is needed in production.
- MongoDB should run as a (single-node) **replica set** so that multi-document operations (issuing a group of barcodes, allocating a storage slot) can use transactions.

---

## 3. Roles and authentication

### 3.1 Roles

| Role | Kind | Summary |
|---|---|---|
| **User** | person | Own profile, samples, frames, measurements, data. |
| **Operator** | person | Everything a User can do for their own account, plus: issue barcodes, fulfil/reject material requests, scan frames through states, lock/unlock frames and edit measurements on behalf of users, view all frames and data, view users' contact details. |
| **Admin** | person | Everything an Operator can do, plus: manage user roles, manage instrument API keys. |
| **Instrument** | service client | Beamline control software. Restricted to the `/api/instrument/*` endpoints (§10.2). Not a person, has no ORCID. |

Roles are hierarchical for persons (User < Operator < Admin). Instrument is separate and has no access to person endpoints.

### 3.2 Person authentication (ORCID)

- Login is **only** via ORCID (OAuth 2.0 / OpenID Connect, ORCID Public API, scope `openid`).
- Flow: browser → ORCID authorize → ORCID redirects to `/mail-in-xas/api/auth/orcid/callback` with a code → backend exchanges code for ORCID iD (+ name if public) → backend looks up user by ORCID iD.
- A `state` parameter protects the flow against forged logins.
- **First login:** user is sent to the *Create account* page (§4). No account exists until that form is submitted.
- After login the portal uses its **own server-side session** (HttpOnly, Secure, SameSite=Lax cookie). ORCID tokens are not kept.
  - Prod cookie path `/mail-in-xas/api/`, dev cookie path `/mail-in-xas/dev/api/`, different cookie names, so prod and dev sessions never mix.
  - Sessions are stored server-side so they can be revoked and role changes take effect immediately.
- **First Admin:** environment variable `BOOTSTRAP_ADMIN_ORCIDS` (comma-separated ORCID iDs). A listed ORCID is given the Admin role on registration/login. Further role changes are made by Admins in the UI.

### 3.3 Dev login (non-production only)

- A fake login page where a developer enters any test ORCID iD and chooses a role.
- Enabled only by an explicit config flag; the endpoint is not registered when the flag is off.
- The backend **refuses to start** if dev login is enabled together with the production configuration.
- Used for local development, the dev environment, and automated tests.

### 3.4 Instrument authentication

- Service clients (e.g. "BL22 control software") are created by an Admin in the portal.
- Each client has one or more **API keys**, shown once at creation, stored only as a hash, individually revocable. Several active keys allow rotation without downtime.
- Sent as `Authorization: Bearer <key>`.
- `/api/instrument/*` is blocked by nginx for requests arriving via the public proxy; the control software calls the backend directly over the internal network.

### 3.5 Actor tracking

Every state change and status change records **who** (user ORCID iD or service-client name) and **when**. This is not a full audit trail, only the last-change information plus the frame's state history (§6.1).

---

## 4. User accounts

### 4.1 Fields

| Field | Required | Notes |
|---|---|---|
| ORCID iD | yes | Unique, immutable, login identity. |
| Name | yes | Taken from ORCID, **not editable**. If ORCID returns no name (private), the user enters it once at registration; it is then also not editable. |
| Email | yes | Confirmed with a code before it is used (§4.3). |
| Phone | yes | Needed for shipping. |
| Affiliation | yes | |
| Shipping address | yes | Exactly one. Fields: c/o (optional), street (1–2 lines), city, state/province (optional), postal code (text, optional), country. Must accept international addresses. |
| Role | yes | Default User. |
| Created at | auto | |

All fields except ORCID iD and name are editable by the user afterwards.

### 4.2 Rules

- Users cannot be deactivated or deleted (for now).
- Operators and Admins can view users' contact details (needed for shipping). Only Admins change roles.

### 4.3 Email confirmation

- Every email address is confirmed with a **6-digit code** sent to it; the user types the code into the portal.
- The code is valid for **60 minutes**, allows 5 attempts and can be resent (at most once per minute; a new code replaces the old one). Codes are stored hashed.
- **Registration** is complete only once the email is confirmed.
- **Changing the email** in the account requires confirming the new address; until then the old address stays in use.
- No emails other than the confirmation code are sent to an unconfirmed address.
- All accounts existing before this feature are test accounts with fake addresses; no migration is needed.

---

## 5. Catalogs

### 5.1 Plate types (fixed for now)

Plate types are maintained by Admins but **seeded and fixed** in this version (no editing UI).

| Plate type | Positions | Mountable on | Other side |
|---|---|---|---|
| 8-Circle | A–H | Left or Right | free |
| 8-Slot | A–H | Left or Right | free |
| 6-Circle-Gas | A–F | **Left only** | **blocked** (the plate spans the whole frame) |

"Gas" = for gas-sensitive samples. (v1's 8-Circle-Gas plate is obsolete and not implemented.)

Each plate type is stored as data: name, position labels, allowed sides, whether it blocks the other side, and drawing information (image + position coordinates) for the interactive frame view. Images and position layouts are taken from v1. A future special plate needs only a new catalog entry.

### 5.2 Position identifier

`<Side>-<Label>`, e.g. `Left-A`, `Right-D`. Side ∈ {Left, Right}.

### 5.3 Measurement options

| Option | Values |
|---|---|
| Technique | XANES, EXAFS (fixed beamline presets) |
| Element | Ti (Z = 22) to Bi (Z = 83) for now |
| Edge | K, L1, L2, L3 |
| Detection | Transmission; Transmission + TFY; Transmission + SDD |
| Beam | Unfocused (default); Focused |

Number of sweeps is decided by the control software, not the user.

**Beamline energy range:** users can only choose an element edge whose energy E0 (X-Ray Data Booklet table) lies within the beamline's energy range, for XANES and EXAFS alike. Default for BL 2-2: **4.7–33 keV**; Admins change it on **Admin → Beamline** (applies immediately; only values differing from the default are stored). Elements without any edge in range are not offered; the measurement dialog disables out-of-range edges and shows E0. New measurements and changes of element or edge are checked by the backend; existing measurements keep their edge when other settings are edited.

---

## 6. Sample frames and barcodes

### 6.1 Frame / barcode

A **frame** is the physical holder; it carries a unique **barcode** and up to two **plates** (Left, Right). A frame record exists from the moment its barcode is reserved.

- **Barcode format:** `XXXX-XXXX`, uppercase letters A–Z, generated server-side, unique, **never reused**. Encoded as **Code128** (1D).
- Operators print labels manually on a handheld label printer; the portal shows the reserved codes so they can be typed/printed.
- Each frame stores: barcode, owner (once issued), state, lock flag, safety declaration, internal-storage location (when applicable), plates, an optional free-text **note** by the user (e.g. "batch 2, Fe catalysts"; editable until the safety declaration), state history (state, actor, timestamp).

### 6.2 Frame states

| State | Meaning |
|---|---|
| `reserved` | Barcode generated (label printed), not assigned to anyone. |
| `issued` | Assigned to a user (as part of a fulfilled material request). |
| `shipped_to_user` | Sent to the user with plates and screws. |
| `received` | Arrived at the facility, safety declared. |
| `received_on_hold` | Arrived at the facility, safety **not** declared. Will not be measured. |
| `external_storage` | Out of robot reach (glove box, desiccator, …). |
| `internal_storage` | In robot reach; has a container (0–2) and slot (0–10). |
| `scheduled` | Selected by the control software's scheduler. |
| `loaded` | Loaded for measurement by the control software. |
| `returned` | Shipped back to the user. Terminal. |
| `void` | Lost/damaged/cancelled barcode. Terminal. |

### 6.3 Transitions

| From | To | Triggered by | Preconditions / effects |
|---|---|---|---|
| `reserved` | `issued` | Operator (scan group, fulfilling a material request) | Exactly M frames scanned for a request with M frames; owner set. |
| `issued` | `shipped_to_user` | Operator (group per user, see §9.3) | |
| `shipped_to_user` | `received` | Operator scan | Safety declared. If **not locked** → warning shown to operator and user. |
| `shipped_to_user` | `received_on_hold` | Operator scan | Safety not declared. Warning shown to operator and user. |
| `received_on_hold` | `received` | **Automatic** | When the user declares safety. |
| `received_on_hold` | `returned` | Operator scan | Typically after a few days, unmeasured. |
| `received` | `external_storage` | Operator scan | |
| `received` | `internal_storage` | Operator scan (single frame) | Free container + slot required. |
| `external_storage` | `internal_storage` | Operator scan (single frame) | Free container + slot required. |
| `internal_storage` | `external_storage` | Operator scan | Frees the slot. |
| `internal_storage` | `scheduled` | Instrument | Frame must be **locked**. |
| `scheduled` | `internal_storage` | Instrument | Scheduler dropped the frame. |
| `scheduled` | `loaded` | Instrument | |
| `loaded` | `internal_storage` | Instrument | Returns to the same slot. |
| `scheduled`, `loaded` | `internal_storage` | Operator (**release**) | Override for when the control software has crashed: the operator puts the frame back manually, then releases it in the portal before restarting the control software. Returns to the same slot. |
| `received`, `external_storage`, `internal_storage` | `returned` | Operator scan | Frees the slot if any. |
| any non-terminal | `void` | Operator | Frees the slot if any. |

All other transitions are rejected by the backend.

- A frame keeps its container/slot while `scheduled` or `loaded`; the slot is freed only when the frame leaves to `external_storage`, `returned` or `void`.
- A container/slot can be occupied by only one frame (enforced by a unique constraint).

### 6.4 Lock and safety declaration

These are flags, independent of the frame state, but ordered: **a frame can only be locked after it has been declared safe.**

**Safety declaration**
- Per frame (covers all samples on it): the user ticks the checkbox *"I declare that all samples on this frame are solid and non-hazardous."*
- Only the frame's owner can declare it. **No one** (not even Admin) can set it on their behalf or override it.
- Requires a valid frame (§6.5).
- Once declared, it cannot be withdrawn.
- **Freezes** the frame's plates, the sample placement, and the samples on it (§8.2).
- Stored with timestamp and actor.

**Lock**
- The user locks the frame before shipping it back.
- Requires the safety declaration (and therefore a valid frame).
- **Freezes** the measurements. Unlocking reopens only the measurements.
- User or Operator can lock and unlock. **No one can unlock while the frame is `scheduled` or `loaded`.**
- A frame must be locked to become `scheduled`.

Resulting combinations: not safe & unlocked (being assembled), safe & unlocked (declared, measurements still editable), safe & locked (ready). "Locked but not safe" cannot occur.

### 6.5 Frame validity (required for the safety declaration)

- At least one side has a plate (either side may be empty).
- Each plate has at least one occupied position.
- Each occupied position has a sample and at least one measurement.
- A position without a sample cannot have measurements.

### 6.6 What can be edited when

| Frame situation | Plates, sample placement, samples | Measurements |
|---|---|---|
| not declared safe | editable (owner) | editable (owner, Operator) |
| declared safe, unlocked | **fixed** | editable (owner, Operator) |
| locked | fixed | fixed (unlock first) |
| `scheduled` / `loaded` | fixed | fixed (cannot unlock) |
| `returned` / `void` | fixed | fixed |

### 6.7 Warnings (notifications, v1)

For now, notifications are **warning texts in the portal**, shown on the user's dashboard and in the operator views:
- frame received but not locked,
- frame received on hold (safety not declared).

Email notifications: §6.8.

### 6.8 Email notifications

Sent **immediately** (via an outbox in the database and a background sender, with retries; web requests never wait for the mail server). No user preferences: users receive all notifications meant for them.

| Event | Trigger | User (owner) | Operators |
|---|---|---|---|
| Material request submitted | user submits a request | – | ✓ |
| Material shipped | operator marks frames as shipped (Shipping page) | ✓ one email per shipment, listing frames and plates | – |
| Frame and samples arrived | receive → `received` | ✓ | – |
| Frame on hold | receive → `received_on_hold` | ✓ (what is missing) | ✓ |
| Frame complete (data ready) | every measurement on the frame is `done` and has data | ✓ with a link to the data page | ✓ |
| Frame returned | return → `returned` | ✓ | – |

- **Operators** = all accounts with the Operator or Admin role.
- No emails about measurement errors: the control software notifies staff about errors itself.
- **From:** "BL22" with a no-reply sender address; no reply-to (the mail server cannot receive mail). Each email says that replies are not read and has a footer linking to the beamline website, https://www-ssrl.slac.stanford.edu/ssrl/web/beam-lines/2-2 (contact details to be added later).
- Plain text plus simple HTML, with links into the portal.
- SMTP connection, sender address and the portal's public URL come from the server environment, never from the repository.
- **Admin → Email:**
  - a **global switch** that turns all notification emails off (confirmation codes are still sent, so users can register);
  - an optional **redirect address**: when set, every email meant for a user or operator goes to this address instead (subject marked with the intended recipient), for troubleshooting without bothering users;
  - the most recent emails with their status (queued, sent, failed with the error);
  - a "send test email" button.
- Dev and local environments send to a local mail catcher or a fixed test address, never to real users.

---

## 7. Material requests

- A user requests plates by type and a number of frames:
  - lines: (plate type, quantity N₁), (plate type, quantity N₂), …; total plates ΣN ≥ 1
  - frames M with **N_gas + ⌈(ΣN − N_gas) / 2⌉ ≤ M ≤ ΣN**, where N_gas is the number of plates that block the other side (6-Circle-Gas), since each of them needs a frame of its own
  - a request may contain **frames only** (ΣN = 0); then M ≥ 1
  - plates, frames and screws are shipped; no return labels.
- States: `submitted` → `issued` → `fulfilled`, or `submitted` → `rejected`. All-or-nothing; no partial issuing.

  | State | Meaning | Operator sees | User sees |
  |---|---|---|---|
  | `submitted` | waiting for an operator | Open | Submitted |
  | `issued` | barcodes issued, frames being packed | Issued (to be shipped) | Being prepared |
  | `fulfilled` | all frames of the request shipped | Fulfilled | Shipped (with barcodes) |
  | `rejected` | declined | Rejected | Rejected (with reason) |

- **Issue:** an Operator opens the request, scans exactly M `reserved` barcodes, and confirms → all M frames become `issued` to the requesting user, request becomes `issued`.
- **Fulfilled** automatically when the last frame of the request is marked shipped (§9.3).
- **Reject:** Operator, with an optional reason shown to the user; only while `submitted`.
- Users cannot cancel or edit a submitted request.
- Plates are **not tracked**: the request records which plates were asked for, so the operator knows what to pack. Only barcodes (frames) are tracked. Users may assemble any plate type from the catalog (§8.1).

---

## 8. Samples, frame assembly and measurements

### 8.1 Frame assembly (user)

Similar to v1's *Create* page:
1. Choose a frame from a **dropdown of barcodes issued to this user** (state `issued` or `shipped_to_user`).
2. Choose a plate type for Left and/or Right (any catalog type; one side may be empty; side rules of §5.1 apply, e.g. 6-Circle-Gas only Left and then no Right plate).
   - Changing or removing a plate whose positions hold samples asks for confirmation and then clears the affected positions, including their measurements (only possible before the safety declaration, §6.6).
3. Click a position on the plate drawing → assign one of the user's samples. The **sample picker** lists non-archived samples, newest first (by creation date).
4. Add measurements to occupied positions.
5. Declare safety and lock.

### 8.2 Samples

- Owned by one user. Fields: name (not unique), free-text description, optional MSDS.
- **MSDS:** PDF only, < 1 MB, at most one per sample. Upload, replace, download.
- A sample can be placed on **several frames**, but **at most once per frame**. One position holds exactly one sample. Replicates of the same material on one frame are separate samples with their own names. The sample picker cannot choose a sample that already sits at another position of the frame; to move it, clear its position first.
- The Samples page lists, per sample, the frames it is placed on (each linking to the frame) and, for frames with data of that sample, a link that opens the data viewer on the sample's position.
- **Frozen:** a sample cannot be edited (name, description, MSDS) once it is placed on any frame that has been declared safe. It stays frozen permanently, also after the frame is returned. A frozen sample can still be placed on new frames.
- **Archive:** the user can archive and un-archive a sample at any time. Archived samples are hidden from the sample picker and the default sample list; a "show archived" option lists them. Archiving changes nothing else.
- **Delete (permanent):** allowed only if the sample has **no data** and every frame it is placed on is either
  - **not yet declared safe** (still being assembled), or
  - already `returned` / `void`.

  Rationale: the portal has no "in transit to facility" state, and a frame cannot be shipped back without the safety declaration. Blocking deletion on any frame that is declared safe and not yet returned/void therefore covers frames in transit and at the facility (`received` through `loaded`, incl. `received_on_hold`), and never leaves an empty position on a declared frame.
  - Deleting a sample from a frame that is still being assembled clears its positions and removes their (never executed) measurements.
  - A sample with data can never be deleted (archive it instead).

### 8.3 Measurements

- Attached to a **position** (not to a sample). A position can have several measurements.
- Fields:

| Field | Notes |
|---|---|
| Measurement number | Short, human-readable integer that numbers the measurements **within one position**: 1, 2, 3, … The counter is separate for each position and starts at 1 on every position. Assigned automatically by the backend when the measurement is created; it never changes afterwards and does not depend on batch or sweep numbers. Never reused, even if a measurement is deleted. **Barcode + location + measurement number** identify exactly one measurement (e.g. "AAAA-AABC Left-B measurement 2"). Shown in the UI and used in export file names (§11.5) to prevent name collisions between measurements that differ only in detection or beam. Internally, measurements also have a database ID, which the API uses. |
| Technique, element, edge, detection, beam | §5.3 |
| Status | `pending` (on creation) → `done` or `error`; set by Instrument. |
| Error message | Optional, set by Instrument with `error`, shown to the user. |
| Last change | actor + timestamp |

- Status is visible to the user.
- **Re-measure:** Operator or Instrument sets the status back to `pending` (clearing any error). The next data uploaded starts a new batch.
- Editing a measurement definition never changes data already collected; each data record carries its own metadata describing what was actually measured.
- A measurement cannot be deleted once it has been executed, i.e. once its status has left `pending` for the first time or any data references it (data is never deleted).
- Export file names and the data viewer take technique/element/edge/detection/beam from the data's own metadata, not from the (possibly edited) current definition.

---

## 9. Operator workflows and scanning

Barcode scanners are handheld devices that emulate a keyboard: a scan types the code followed by Enter into a focused input field.

### 9.1 Scan frames page (one table, per-frame actions)

Used for: **receive**, **to external storage**, **return to user**, **void**. (Issuing barcodes and shipping to users have their own pages, §7 and §9.3.)

- Scanned codes collect in **one table**: barcode, user, current status, safety and lock flags.
- Each row has **one button per action**. A button is enabled only if that move is possible for the frame; its tooltip names the action, adds a warning if any (e.g. not declared safe: put on hold; not locked), or explains why the move is not possible.
- Clicking moves that one frame. **Void** asks for confirmation first (it cannot be undone).
- After an action the row **stays** in the table: it shows the frame's new status, the **last action** taken, and is marked as handled (green background), so further actions on the same frame need no rescan.
- Receive: frames without safety declaration become `received_on_hold`; frames that are not locked become `received` with a warning.
- Unknown barcodes are highlighted. Duplicate scans of the same code are ignored. Rows can be removed individually or all at once (Clear).

### 9.2 Move to internal storage (single frame)

Batch scanning is **not** allowed here.
1. Scan one frame.
2. Enter container (0–2) and slot (0–10).
3. Save. The backend rejects occupied slots and invalid transitions.

### 9.3 Issued-not-shipped view

Lists all `issued` frames grouped by user (with the user's shipping address and phone). The operator can mark a whole group as `shipped_to_user`.

### 9.4 Internal storage view

Table of all frames in internal storage and their positions: barcode, container, slot, state, lock flag, measurement progress ("3 done · 1 failed · 2 pending"). Used to find and remove processed frames.

- A frame waiting in its slot with **failed measurements** (status `error`) is marked **red** in the grid with "N failed"; hovering lists each failed measurement (position, number, technique, edge, error message). The control software's queue only takes pending measurements, so such a frame waits for a decision by staff. No "ready to remove" marker and no warning on the Home page (decided 2026-10-16). Re-measure from the portal is not offered yet (§8.3: API only).

### 9.5 Other operator views

- Material requests (submitted / fulfilled / rejected).
- Barcode reservation: generate N new codes (`reserved`) and list them for printing.
- All frames, filterable by state and user; frame detail with state history.
- Warnings list (§6.7).
- **Server-side paging** for the lists that grow with every user: All Frames, All Users and Material Requests (operator). The server searches, filters, sorts and pages (`page`, `page_size` 25/50/100, max 200, `q`, `sort`, `order`) and returns one page with the total number of matches; the search waits for a pause in typing (0.3 s). Search: All Frames by start of the barcode, owner name or note; All Users by name, ORCID iD, email or affiliation (filter by role); Material Requests by request number or user name. A user's own lists (My Samples, the sample picker, My Frames, own requests) stay unpaged until they grow large.

---

## 10. REST API

Base path: `/mail-in-xas/api` (prod), `/mail-in-xas/dev/api` (dev). The list below shows resources and intent; exact paths and payloads will be defined in the OpenAPI spec.

### 10.1 Portal API (sessions)

| Area | Endpoints (indicative) | Access |
|---|---|---|
| Auth | `GET /auth/orcid/login`, `GET /auth/orcid/callback`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/dev-login` (dev only) | public / any |
| Account | `POST /users` (create account after first login), `GET/PUT /users/me` | User |
| Users | `GET /users`, `GET /users/{id}` | Operator |
| Roles | `PUT /users/{id}/role` | Admin |
| Service clients | `GET/POST /service-clients`, `POST /service-clients/{id}/keys`, `DELETE /service-clients/{id}/keys/{keyId}` | Admin |
| Catalogs | `GET /plate-types`, `GET /measurement-options` | User |
| Material requests | `POST /material-requests`, `GET /material-requests` (own; all for Operator), `POST /material-requests/{id}/fulfil` (barcodes), `POST /material-requests/{id}/reject` | User / Operator |
| Barcodes | `POST /barcodes/reserve` (count), `GET /barcodes?state=…` | Operator |
| Frames | `GET /frames` (own; all for Operator), `GET /frames/{barcode}`, `PUT /frames/{barcode}/plates`, `PUT /frames/{barcode}/positions/{position}` (assign/clear sample), `POST /frames/{barcode}/lock`, `POST /frames/{barcode}/unlock`, `POST /frames/{barcode}/declare-safe` | owner / Operator (declare-safe: owner only) |
| Measurements | `POST /frames/{barcode}/positions/{position}/measurements`, `PUT/DELETE /measurements/{id}`, `POST /measurements/{id}/remeasure` | owner / Operator (remeasure: Operator) |
| Samples | `GET/POST /samples`, `GET/PUT/DELETE /samples/{id}`, `PUT/GET/DELETE /samples/{id}/msds` | owner |
| Scanning | `POST /scans/validate` (codes + action → per-code result), `POST /scans/apply` (codes + action), `POST /frames/{barcode}/internal-storage` (container, slot) | Operator |
| Storage | `GET /storage/internal` | Operator |
| Warnings | `GET /warnings` (own; all for Operator) | User / Operator |
| Data | `GET /frames/{barcode}/sweeps` (all sweeps without values: measurement, batch, sweep, what was measured, channels, available spectra), `GET /sweeps/{id}` (metadata), `GET /sweeps/{id}/curve?view=raw\|spectrum&name=…`, `GET /measurements/{id}/batches/{batch}/merge?view=…&name=…&sweeps=…`, `GET /measurements/{id}/batches/{batch}/process?spectrum=…&sweeps=…` (§11.2) | owner / Operator |
| Export | `GET /frames/{barcode}/export.zip` | owner / Operator |
| XAS parameters | `GET/PUT/DELETE /admin/xas-parameters` (list, change, restore defaults) | Admin |
| Email confirmation | `POST /users/me/email/confirm` (code), `POST /users/me/email/code` (resend), `DELETE /users/me/email/pending` (withdraw a change) | own account |
| Email (admin) | `GET/PUT /admin/mail` (status, switch, redirect), `GET /admin/mail/outbox`, `POST /admin/mail/test` | Admin |

### 10.2 Instrument API (API key, internal network only)

| Purpose | Endpoint (indicative) |
|---|---|
| Measurement definitions for one frame (positions, samples, measurements incl. status, last batch and sweep numbers) | `GET /instrument/frames/{barcode}` |
| All frames in internal storage (barcode, container, slot, state, locked) | `GET /instrument/storage/internal` |
| Locked frames in internal storage with their pending measurements | `GET /instrument/queue` |
| Change frame state (`scheduled`, `loaded`, back to `internal_storage`) | `POST /instrument/frames/{barcode}/state` |
| Set measurement status (`pending`, `done`, `error` + message) | `PUT /instrument/measurements/{id}/status` |
| Upload raw sweep data | `POST /instrument/measurements/{id}/sweeps` |

Upload rules:
- The control software sends `batch_no` and `sweep_no` with each raw upload; it chooses them (the frame endpoint reports each measurement's last batch and sweep). A **re-measure** sets the status back to `pending` (API only for now); the re-run then uses the next batch number and continues the sweep numbers.
- `(measurement, batch_no, sweep_no)` must be unique → a retried upload returns a conflict instead of creating a duplicate.
- `batch_no` and `sweep_no` are **1…999**; a `sweep_no` exists only once per measurement (across batches).
- The backend copies frame, position, sample and owner from the measurement into each sweep (never from the upload) and stores a snapshot of the measurement's settings, so data and references stay consistent.
- Requests are limited to 12 MB (a sweep is typically ~1 MB, at most ~5 MB).
- Batches may contain different numbers of sweeps.
- Raw data is immutable: no endpoint updates or deletes it.
- The control software uploads raw data only; processing is done by the portal (§11.2).

---

## 11. Data

### 11.1 Raw sweep record (uploaded after each sweep)

- Keys: measurement, frame barcode, position, batch_no, sweep_no, upload time.
- **Metadata** (free-form dictionary), including at least: what was actually measured (technique, element, edge, detection, beam), encoder calibration, crystal (lattice) spacing, ADC-to-voltage calibration, SDD ROI bin start and width per ROI (integers).
- **Channels:** list of `{name, unit, values[]}`, all of equal length.

| Channel | Unit | Present |
|---|---|---|
| `energy` | eV | always |
| `encoder` | counts | always |
| `i0`, `i1`, `i2` | V | always |
| `fy` | V | always (PIPS photodiode) |
| `roi1_n`, `roi2_n` | counts/s | with SDD; n = detector element |
| `OCR_n` | counts/s | with SDD |
| `LiveTime_n` | s | with SDD |

The channel set is not fixed; the backend stores whatever named channels are sent.

All analog channels are always recorded, even when they carry no meaningful signal (e.g. `fy` in transmission mode when the photodiode is not deployed, or `i1`/`i2` in fluorescence mode on a thick sample). The data viewer pre-selects the spectrum that matches the detection mode (transmission → `sample_trans`, TFY → `fy_norm`, SDD → `sdd_roi1`) but lets the user plot any channel.

### 11.2 Processing (computed by the portal on request, not stored)

- **Input:** the spectrum selected in the viewer (§11.3; by default the one matching the detection mode) of the checked sweeps of one batch. One sweep is processed as is; **several are merged first** and the merge is processed.
- **Steps:**
  1. **E0** from the X-Ray Data Booklet table (https://xdb.lbl.gov) for the measurement's element and edge (not derived from the data; energy alignment comes later).
  2. **Normalisation:** pre-edge quadratic polynomial from 10 eV after the start of the spectrum to 40 eV below E0; post-edge cubic polynomial from 150 eV above E0 to 10 eV before the end; edge step = post-edge minus pre-edge at E0.
  3. **Background removal** (AUTOBK-like): a cubic spline in k whose coefficients minimise the Fourier components of χ below R_bkg = 1 Å.
  4. **χ(k)**, shown k²-weighted.
  5. **Fourier transform** χ(R) (magnitude, real and imaginary part) with a Hanning window: k from 2 Å⁻¹ to 1 Å⁻¹ before the end of the data, taper dk = 1 Å⁻¹, R up to 6 Å.
- **Parameters:** the defaults are collected in one class in the code (`backend/app/processing/parameters.py`). Admins can change the scientific ones (ranges, polynomial orders, R_bkg, k-weights, FT window) on **Admin → XAS parameters**, with allowed ranges, Apply and Restore defaults; only values that differ from the defaults are stored, and changes apply to all users immediately (no restart). Technical settings (k grid, FFT size, plotted ranges) are changed in the code only. No history of changes is kept. The parameters used are shown with every result and written into the headers of exported files.
- If a step is not possible (e.g. a XANES scan has no post-edge or EXAFS region), the steps before it are still shown, with the reason.
- Dead-time: SDD data is assumed to be dead-time corrected already (open item 3).

### 11.3 Derived spectra (computed on request by the backend, not stored)

| Spectrum | Formula |
|---|---|
| `sample_trans` | ln(i0 / i1) |
| `ref_trans` | ln(i1 / i2) |
| `fy_norm` | fy / i0 |
| `sdd_roi1` | Σₙ roi1_n / i0 |
| `sdd_roi2` | Σₙ roi2_n / i0 |

- **Merge:** within **one batch** only, over the sweeps the user selects (or all sweeps of the batch). Sweeps are linearly interpolated onto the first selected sweep's energy grid, within the range all of them cover, and averaged. Merged data is neither stored nor exported.

### 11.4 Data viewer (user)

1. Select frame → position → measurement → batch.
2. Choose view:
   - **Raw signals:** any individual channel (e.g. `i0`, `i1`, `fy`, `roi1_3`) vs energy,
   - **Spectra:** derived spectra (§11.3),
   - **μ(E)** (raw, not normalised) with the pre-edge, post-edge and background curves, each can be shown or hidden,
   - **χ(k)** (k²-weighted),
   - **χ(R)**: magnitude, optionally real and imaginary part.
3. Spectra and raw signals: all sweeps of the selected measurement/batch are overlaid; sweeps can be toggled; the merge of all sweeps and the merge of the checked sweeps can be shown.
4. μ(E), χ(k), χ(R): the processing (§11.2) of the checked sweep, or of the merge of the checked sweeps.
5. Metadata of each sweep, and E0, edge step and processing parameters, are shown alongside.

Overlay across different measurements or positions is not required.

### 11.5 Export

- One **ZIP per frame**, built on request (typically a few hundred kB to < 10 MB).
- One folder per position/sample: `<Location>_<SampleName>` (sample name sanitized for file systems), e.g. `Left-G_V2O5/`.
- Files in **XDI** format (ASCII). Header contains the metadata; columns are the channels.
- File name: `<Barcode>_<MeasNo>_<Location>_<Element>_<Edge>_<Type>_<BatchNo>_<SweepNo>.xdi`
  - MeasNo and BatchNo without leading zeros; SweepNo 3 digits zero-padded.
  - Example raw: `AAAA-AABC_7_Left-G_V_K_EXAFS_1_002.xdi`
  - Processed (§11.2, computed at export time for each sweep's default spectrum): up to three files per sweep, since the x-axes differ:
    - `AAAA-AABC_7_Left-G_V_K_EXAFS_1_002_proc_mu.xdi` (energy, μ, pre-edge, post-edge, background)
    - `AAAA-AABC_7_Left-G_V_K_EXAFS_1_002_proc_chi.xdi` (k, k²χ)
    - `AAAA-AABC_7_Left-G_V_K_EXAFS_1_002_proc_chir.xdi` (R, |χ(R)|, Re, Im)
  - Steps that are not possible for a sweep are left out (no processed files at all if not even the normalisation works).
- Example: Left-A has Cu K EXAFS (transmission); Left-B has Cu K EXAFS (transmission) and Cu K EXAFS (SDD). Left-B's SDD measurement is re-measured, giving batch 2. Files:
  ```
  Left-A_<sample>/AAAA-AABC_1_Left-A_Cu_K_EXAFS_1_001.xdi
  Left-B_<sample>/AAAA-AABC_1_Left-B_Cu_K_EXAFS_1_001.xdi
  Left-B_<sample>/AAAA-AABC_2_Left-B_Cu_K_EXAFS_1_001.xdi
  Left-B_<sample>/AAAA-AABC_2_Left-B_Cu_K_EXAFS_1_002.xdi
  Left-B_<sample>/AAAA-AABC_2_Left-B_Cu_K_EXAFS_2_003.xdi   ← batch 2, sweep numbering continues
  ```
- Contains raw and processed data for every sweep; no merged data. E0, edge step and all processing parameters are in the headers of the processed files.

### 11.6 Storage notes

- Typical sweep records are well below MongoDB's 16 MB document limit; arrays are stored in a separate collection from frame/measurement documents so frequent queries stay small.
- MSDS PDFs are stored in GridFS (or a dedicated collection).
- No embargo, no retention policy, no deletion of raw data.
- Version 2 keeps all data in MongoDB. The MongoDB server's disk is limited; moving the sweep data out of MongoDB (files) is planned for version 3.
- **Admin → Status** shows the MongoDB disk (used, free, total; yellow from 80 %, red from 90 %), the size of the portal's database and of each collection, and the sweeps uploaded in the last 30 days with the time until the disk is full at that rate. The disk figures are those of the whole MongoDB server, which other databases share. The page can later show other system information.

---

## 12. Non-functional requirements

| Topic | Requirement |
|---|---|
| Scale | ~1000 users total, < 10 concurrent. |
| Concurrency | A frame belongs to one user; concurrent edits by owner and Operator are rare. Optimistic version check on frame updates to avoid silent overwrites. |
| Security | Server-side sessions; HttpOnly/Secure/SameSite cookies; all input validated (Pydantic); ownership checked on every resource; instrument endpoints blocked publicly; API keys hashed; MongoDB authentication enabled and ports firewalled to the VM/internal hosts. |
| Origin sharing | The portal shares the origin `www-ssrl.slac.stanford.edu` with other SSRL pages; path-scoped HttpOnly cookies mitigate but do not eliminate this risk. Accepted, since the URL is fixed. |
| TLS | Ends at the SLAC reverse proxy. Internal traffic is plain HTTP for now. |
| Sub-path hosting | Vite `base` and React Router base path set per environment; FastAPI configured with the proxy path prefix. |
| Environments | Prod and dev on the same VM, separate backends, separate databases, separate ORCID clients (local development: ORCID sandbox with `http://localhost` callback, or dev login; dev environment on the VM: dev login). Dev reachable only directly on the VM's internal hostname. |
| Browser support | Current versions of Chrome, Firefox, Edge, Safari. |
| Availability | Best effort; no formal uptime requirement. |

### 12.1 SLAC reverse proxy (tested 2026-10-17 with `tools/proxy_probe.py`)

SLAC's reverse proxy (HAProxy, load balanced) terminates TLS and forwards
`https://www-ssrl.slac.stanford.edu/mail-in-xas/` to port 80 of the app VM over plain HTTP.

| Question | Result |
|---|---|
| Path forwarded unchanged? | Yes, the whole `/mail-in-xas/` tree including `/mail-in-xas/dev/` and query strings. Dev must therefore be blocked by our nginx. |
| Headers | `Host` and `X-Forwarded-Host` = `www-ssrl.slac.stanford.edu`, `X-Forwarded-Proto: https`, `X-Forwarded-URI`, `x-client-ip` (client address). `X-Forwarded-For` arrives as one header line per hop; nginx joins them. The backend does not depend on these headers (cookie security and the ORCID callback come from settings). |
| Proxy address | All test requests came from one address (set on the VM only; not in this public repository). Other nodes of the load-balanced proxy may use others: asked the proxy owners. nginx therefore also treats any request with `X-Forwarded-Host` as proxied, so dev and the instrument API stay closed if the addresses change. |
| Limits | 12 MB upload passed, 20 MB download passed, no timeout up to 150 s (needed: 12 MB uploads, ~10 MB downloads, 120 s). Upper limits: asked the proxy owners. |

---

## 13. Open items

| # | Topic | Status |
|---|---|---|
| 1 | ORCID: production Public API client registered under the project lead's personal ORCID account for now (handover plan needed if ownership changes; SLAC institutional membership may be considered later). A sandbox client (sandbox.orcid.org) is used for local development with an `http://localhost` callback, believed to be accepted by the sandbox; confirm at registration. | Production client registered (2026-10-15, redirect URI `https://www-ssrl.slac.stanford.edu/mail-in-xas/api/auth/orcid/callback`); credentials kept by the project lead for the production `.env` |
| 2 | MongoDB backups: who, how often, where. | TBD |
| 3 | SDD dead-time: ROI rates are **not** dead-time corrected (confirmed 2026-10-17); a correction using OCR/LiveTime is needed. | Later |
| 4 | Email notifications: specified in §6.8 and §4.3. Slack notifications for staff. | Email decided; Slack later |
| 5 | Processed XDI files: `…_proc_mu.xdi`, `…_proc_chi.xdi` and `…_proc_chir.xdi` (§11.5). | Decided |
| 10 | Energy alignment (e.g. to the reference ln(i1/i2)) and user-adjustable processing parameters. | Later |
| 6 | Element/edge restriction to beamline energy range. | Done (§5.3, Admin → Beamline) |
| 7 | Plate-type catalog editing UI. | Later |
| 8 | Internal TLS. | Later |
| 9 | Process manager on the VM: **systemd** (one service per backend: prod and dev). | Decided |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| Frame | Physical, barcoded holder carrying up to two plates. |
| Plate | Sample plate mounted on the Left or Right side of a frame; type from the catalog. |
| Position | `<Side>-<Label>` location on a frame, holds at most one sample. |
| Sample | User-defined material (name, description, optional MSDS); can be placed in several positions. |
| Measurement | Technique/element/edge/detection/beam definition for one position. |
| Batch | One run of a measurement; a re-measure starts a new batch. |
| Sweep | One scan within a batch; numbered 1…999 across all batches of a measurement. |
| Instrument | The beamline control software acting as a service client. |
