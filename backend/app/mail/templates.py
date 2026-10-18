"""Email texts (requirements §6.8, §4.3): subject, plain text and HTML for each kind of email."""

import html
from dataclasses import dataclass
from typing import Any

from app.catalog import PLATE_TYPES

BEAMLINE_URL = "https://www-ssrl.slac.stanford.edu/ssrl/web/beam-lines/2-2"
FOOTER = (
    "This is an automatic message from the BL22 mail-in XAS portal; replies are not read. "
    "Beamline 2-2:"
)


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


def _render(
    subject: str,
    greeting: str | None,
    paragraphs: list[str],
    link: tuple[str, str] | None = None,
    items: list[str] | None = None,
) -> Rendered:
    """A short email: greeting, paragraphs, an optional list and an optional link."""
    text_parts = [greeting] if greeting else []
    html_parts = [f"<p>{html.escape(greeting)}</p>"] if greeting else []
    for paragraph in paragraphs:
        text_parts.append(paragraph)
        html_parts.append(f"<p>{html.escape(paragraph)}</p>")
    if items:
        text_parts.append("\n".join(f"  - {item}" for item in items))
        html_parts.append(
            "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"
        )
    if link:
        label, url = link
        text_parts.append(f"{label}: {url}")
        html_parts.append(f'<p><a href="{html.escape(url)}">{html.escape(label)}</a></p>')
    text_parts.append(f"--\n{FOOTER} {BEAMLINE_URL}")
    html_parts.append(
        '<hr><p style="color:#868e96;font-size:12px">'
        f'{html.escape(FOOTER)} <a href="{BEAMLINE_URL}">{BEAMLINE_URL}</a></p>'
    )
    body = "\n\n".join(text_parts) + "\n"
    page = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px">'
        + "".join(html_parts)
        + "</div>"
    )
    return Rendered(subject, body, page)


def _frames(data: dict[str, Any]) -> list[str]:
    return list(data.get("frames", []))


def _shipped(data: dict[str, Any], hello: str, portal_url: str) -> Rendered:
    """One shipment: new frames and plates, and/or frames returned with the user's samples."""
    new = _frames(data)
    returned = list(data.get("returned", []))
    plates = data.get("plates", [])
    items = [f"Frame {code} (new)" for code in new]
    items += [f"{p['quantity']} × {_plate_name(p['plate_type'])} plate" for p in plates]
    items += [f"Frame {code} with your samples (returned)" for code in returned]
    paragraphs = []
    if new or plates:
        paragraphs.append(
            "We have shipped new material to you. Once it arrives, mount the plates, place "
            "your samples, define the measurements and declare the frames safe in the portal "
            "before sending them back."
        )
    if returned:
        paragraphs.append(
            "Your frames with your samples are on their way back to you. The data of all "
            "measurements stays available in the portal."
        )
    if new and returned:
        subject = f"{len(new)} new and {len(returned)} returned frame(s) shipped to you"
    elif returned:
        subject = f"{len(returned)} frame(s) returned to you"
    else:
        subject = f"{len(new)} frame(s) shipped to you"
    return _render(
        f"BL22 mail-in XAS: {subject}",
        hello,
        paragraphs,
        ("Your frames", f"{portal_url}frames"),
        items,
    )


def _plate_name(type_id: str) -> str:
    plate = PLATE_TYPES.get(type_id)
    return plate.name if plate else type_id


def render(kind: str, data: dict[str, Any], portal_url: str) -> Rendered:
    """portal_url ends with a slash, e.g. https://host/mail-in-xas/."""
    name = data.get("name")
    hello = f"Dear {name}," if name else "Hello,"
    match kind:
        case "email_code":
            return _render(
                "BL22 mail-in XAS: confirm your email address",
                hello,
                [
                    f"Your code to confirm this email address is {data['code']}.",
                    "Enter it in the portal within 60 minutes. If you did not request it, "
                    "you can ignore this email.",
                ],
            )
        case "material_request":
            items = [f"{p['quantity']} × {p['plate_type']} plate" for p in data.get("plates", [])]
            items.insert(0, f"{data['frames']} frame(s)")
            paragraphs = [f"{data['user_name']} submitted material request #{data['number']}."]
            if data.get("comment"):
                paragraphs.append(f"Comment: {data['comment']}")
            return _render(
                f"New material request #{data['number']} from {data['user_name']}",
                None,
                paragraphs,
                ("Open the request", f"{portal_url}operator/requests/{data['request_id']}"),
                items,
            )
        case "shipped":
            return _shipped(data, hello, portal_url)
        case "arrived":
            frames = _frames(data)
            return _render(
                f"BL22 mail-in XAS: {len(frames)} frame(s) arrived",
                hello,
                ["The following frames with your samples have arrived at SSRL."],
                ("Your frames", f"{portal_url}frames"),
                frames,
            )
        case "on_hold":
            return _render(
                f"BL22 mail-in XAS: frame {data['barcode']} is on hold",
                hello,
                [
                    f"Frame {data['barcode']} has arrived at SSRL, but it was not declared "
                    "safe. It stays on hold and will not be measured until you declare it "
                    "safe in the portal.",
                ],
                ("Open the frame", f"{portal_url}frames/{data['barcode']}"),
            )
        case "on_hold_staff":
            return _render(
                f"Frame {data['barcode']} of {data['owner_name']} is on hold",
                None,
                [
                    f"Frame {data['barcode']} of {data['owner_name']} was received without "
                    "a safety declaration and is on hold.",
                ],
                ("Open the frame", f"{portal_url}frames/{data['barcode']}"),
            )
        case "frame_complete":
            return _render(
                f"BL22 mail-in XAS: frame {data['barcode']} is measured, data is ready",
                hello,
                [
                    f"All {data['measurements']} measurement(s) on frame {data['barcode']} "
                    "are complete. You can view and download the data in the portal.",
                ],
                ("View the data", f"{portal_url}frames/{data['barcode']}/data"),
            )
        case "frame_complete_staff":
            return _render(
                f"Frame {data['barcode']} of {data['owner_name']} is complete",
                None,
                [
                    f"All {data['measurements']} measurement(s) on frame {data['barcode']} "
                    f"of {data['owner_name']} are complete and the data is available.",
                ],
                ("View the data", f"{portal_url}frames/{data['barcode']}/data"),
            )
        case "returned":  # no longer sent (now part of "shipped"); kept for queued emails
            return _render(
                f"BL22 mail-in XAS: frame {data['barcode']} returned",
                hello,
                [f"Frame {data['barcode']} is on its way back to you."],
                ("Your frames", f"{portal_url}frames"),
            )
        case "test":
            return _render(
                "BL22 mail-in XAS: test email",
                None,
                ["This is a test email from the BL22 mail-in XAS portal."],
                ("Open the portal", portal_url),
            )
    raise ValueError(f"unknown email kind {kind!r}")
