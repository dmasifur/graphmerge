from __future__ import annotations

import base64
import io
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import mammoth
import requests
from azure.identity import InteractiveBrowserCredential, TokenCachePersistenceOptions
from jinja2 import Environment, StrictUndefined, meta

if TYPE_CHECKING:
    import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_ME_SEND_MAIL = "https://graph.microsoft.com/v1.0/me/sendMail"
GRAPH_USER_SEND_MAIL = "https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail"
GRAPH_ME_MESSAGES = "https://graph.microsoft.com/v1.0/me/messages"
GRAPH_USER_MESSAGES = "https://graph.microsoft.com/v1.0/users/{mailbox}/messages"

MAX_RETRIES = 3
DEFAULT_RETRY_SECONDS = 5
MAX_RETRY_WAIT_SECONDS = 30
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

LARGE_ATTACHMENT_THRESHOLD = 3 * 1024 * 1024
# Upload-session chunk size must be a multiple of 320 KiB (Graph's contract).
UPLOAD_CHUNK_SIZE = 320 * 1024 * 10

# Autoescape covers substituted values only, so HTML templates render intact
# while CSV data cannot inject markup. Subjects and file paths must stay
# unescaped — escaping would corrupt ordinary characters like "&".
_HTML_ENV = Environment(undefined=StrictUndefined, autoescape=True)
_TEXT_ENV = Environment(undefined=StrictUndefined)
_PARSE_ENV = Environment()


@dataclass
class SendResult:
    row: int
    recipient: str
    success: bool
    detail: str = ""


@dataclass
class CampaignConfig:
    client_id: str
    tenant_id: str
    sender_type: str  # "personal" or "shared"
    shared_mailbox: str | None = None
    delay_seconds: float = 0.0


def get_credential(client_id: str, tenant_id: str) -> InteractiveBrowserCredential:
    return InteractiveBrowserCredential(
        client_id=client_id,
        tenant_id=tenant_id,
        cache_persistence_options=TokenCachePersistenceOptions(name="graphmerge"),
    )


def get_access_token(credential: InteractiveBrowserCredential) -> str:
    return credential.get_token(GRAPH_SCOPE).token


def load_template(filename: str, raw_bytes: bytes) -> str:
    """Load an email body template from an uploaded file's raw bytes.

    Word documents are converted to HTML via mammoth; HTML/text files are
    decoded as-is. Both paths yield a plain HTML string ready for
    render_row.
    """
    if filename.lower().endswith(".docx"):
        result = mammoth.convert_to_html(io.BytesIO(raw_bytes))
        return str(result.value)
    return raw_bytes.decode("utf-8")


def render_row(template_str: str, row: dict[str, Any]) -> str:
    """Render an HTML template, HTML-escaping the substituted row values."""
    return _HTML_ENV.from_string(template_str).render(row)


def render_text(template_str: str, row: dict[str, Any]) -> str:
    """Render a plain-text template (subject line, file path) without escaping."""
    return _TEXT_ENV.from_string(template_str).render(row)


def find_missing_placeholders(template_str: str, available_columns: set[str]) -> set[str]:
    """Return template {{placeholders}} that don't match any CSV column (case-insensitive)."""
    ast = _PARSE_ENV.parse(template_str)
    referenced = meta.find_undeclared_variables(ast)
    available_lower = {c.lower() for c in available_columns}
    return {v for v in referenced if v.lower() not in available_lower}


def validate_recipients(df: pd.DataFrame, col_map: dict[str, str]) -> list[str]:
    """Return human-readable problems for rows with syntactically invalid addresses."""
    problems = []
    for i, raw_row in enumerate(df.to_dict(orient="records")):
        row_dict: dict[str, Any] = {str(k): v for k, v in raw_row.items()}
        addresses: list[str] = []
        to = get_field(row_dict, col_map, "To", "email")
        if to:
            addresses.append(str(to))
        for field in ("CC", "BCC"):
            value = get_field(row_dict, col_map, field)
            if value:
                addresses.extend(e.strip() for e in str(value).split(",") if e.strip())

        if not addresses:
            problems.append(f"Row {i + 1}: no recipient address found")
            continue

        for address in addresses:
            if not EMAIL_RE.match(address):
                problems.append(f"Row {i + 1}: '{address}' doesn't look like a valid email address")
    return problems


def normalize_columns(df_columns: set[str]) -> dict[str, str]:
    """Map lowercased column name -> actual column name, for case-insensitive lookup."""
    return {c.lower(): c for c in df_columns}


def get_field(row: dict[str, Any], col_map: dict[str, str], *names: str) -> Any:
    """Case-insensitively find the first present, non-empty value among `names`."""
    for name in names:
        actual = col_map.get(name.lower())
        if actual and row.get(actual):
            return row[actual]
    return None


def resolve_attachment_paths(raw_value: str, row: dict[str, Any]) -> list[str]:
    """Render a semicolon-separated attachment-path cell into a list of paths."""
    rendered = render_text(str(raw_value), row)
    return [p.strip() for p in rendered.split(";") if p.strip()]


def classify_attachments(paths: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split attachment paths into (small, large, missing).

    Paths that don't exist on disk are reported rather than dropped, so a
    campaign never silently sends emails with attachments left off.
    """
    small, large, missing = [], [], []
    for path in paths:
        if not os.path.exists(path):
            missing.append(path)
        elif os.path.getsize(path) > LARGE_ATTACHMENT_THRESHOLD:
            large.append(path)
        else:
            small.append(path)
    return small, large, missing


def validate_attachments(df: pd.DataFrame, col_map: dict[str, str]) -> list[str]:
    """Return human-readable problems for rows referencing attachments that don't exist."""
    problems = []
    for i, raw_row in enumerate(df.to_dict(orient="records")):
        row_dict: dict[str, Any] = {str(k): v for k, v in raw_row.items()}
        value = get_field(row_dict, col_map, "Attachments", "Attachment")
        if not value:
            continue
        try:
            paths = resolve_attachment_paths(value, row_dict)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user as a validation problem
            problems.append(f"Row {i + 1}: couldn't resolve attachment path ({exc})")
            continue
        _, _, missing = classify_attachments(paths)
        for path in missing:
            problems.append(f"Row {i + 1}: attachment not found: {path}")
    return problems


def build_attachments(paths: list[str]) -> list[dict[str, str]]:
    """Build inline Graph fileAttachment payloads for the given (small) paths."""
    attachments = []
    for path in paths:
        with open(path, "rb") as f:
            attachments.append(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": os.path.basename(path),
                    "contentType": "application/octet-stream",
                    "contentBytes": base64.b64encode(f.read()).decode("utf-8"),
                }
            )
    return attachments


def build_message(
    row: dict[str, Any], subject_template: str, body_template: str, col_map: dict[str, str]
) -> tuple[dict[str, Any], list[str]]:

    message: dict[str, Any] = {
        "subject": render_text(subject_template, row),
        "body": {"contentType": "HTML", "content": render_row(body_template, row)},
        "toRecipients": [],
    }

    recipient = get_field(row, col_map, "To", "email")
    if not recipient:
        raise ValueError("Missing 'To' or 'email' value for this row")
    message["toRecipients"] = [{"emailAddress": {"address": str(recipient).strip()}}]

    cc = get_field(row, col_map, "CC")
    if cc:
        message["ccRecipients"] = [
            {"emailAddress": {"address": e.strip()}} for e in str(cc).split(",") if e.strip()
        ]

    bcc = get_field(row, col_map, "BCC")
    if bcc:
        message["bccRecipients"] = [
            {"emailAddress": {"address": e.strip()}} for e in str(bcc).split(",") if e.strip()
        ]

    large_paths: list[str] = []
    attachment_value = get_field(row, col_map, "Attachments", "Attachment")
    if attachment_value:
        paths = resolve_attachment_paths(attachment_value, row)
        small_paths, large_paths, missing_paths = classify_attachments(paths)
        if missing_paths:
            raise ValueError(f"Attachment file(s) not found: {', '.join(missing_paths)}")
        if small_paths:
            message["attachments"] = build_attachments(small_paths)

    return message, large_paths


def parse_retry_after(value: str | None, fallback: int) -> int:
    """Seconds to wait per a Retry-After header, clamped to a sane range.

    Graph sends an integer count of seconds. Anything else (an HTTP-date, a
    malformed value) falls back to the caller's backoff rather than raising.
    """
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        seconds = fallback
    return max(0, min(seconds, MAX_RETRY_WAIT_SECONDS))


def _require_mailbox(config: CampaignConfig) -> str | None:
    """Return the shared mailbox to send as, or None for the signed-in user's own mailbox.

    Raises if a shared send was requested without naming a mailbox, so the
    campaign fails loudly instead of quietly sending from the personal mailbox.
    """
    if config.sender_type != "shared":
        return None
    mailbox = (config.shared_mailbox or "").strip()
    if not mailbox:
        raise ValueError("Sending from a shared mailbox requires a shared mailbox address")
    return mailbox


def send_mail_endpoint(config: CampaignConfig) -> str:
    mailbox = _require_mailbox(config)
    return GRAPH_USER_SEND_MAIL.format(mailbox=mailbox) if mailbox else GRAPH_ME_SEND_MAIL


def messages_endpoint(config: CampaignConfig) -> str:
    mailbox = _require_mailbox(config)
    return GRAPH_USER_MESSAGES.format(mailbox=mailbox) if mailbox else GRAPH_ME_MESSAGES


def _request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    credential: InteractiveBrowserCredential,
    **kwargs: Any,
) -> tuple[requests.Response | None, str | None]:

    extra_headers = kwargs.pop("headers", {})
    for attempt in range(1, MAX_RETRIES + 1):
        token = get_access_token(credential)
        headers = {"Authorization": f"Bearer {token}", **extra_headers}

        try:
            response = session.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            return None, f"Network error: {exc}"

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
            backoff = min(DEFAULT_RETRY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_WAIT_SECONDS)
            time.sleep(parse_retry_after(response.headers.get("Retry-After"), backoff))
            continue

        return response, None

    return None, "Failed after retries"


def send_via_graph(
    session: requests.Session,
    credential: InteractiveBrowserCredential,
    message: dict[str, Any],
    config: CampaignConfig,
) -> tuple[bool, str]:
    """Send one message via Graph, retrying on throttling/transient errors."""
    endpoint = send_mail_endpoint(config)
    payload = {"message": message, "saveToSentItems": "true"}

    response, error = _request_with_retry(
        session,
        "POST",
        endpoint,
        credential,
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    if response is None:
        return False, error or "Failed after retries"

    if response.status_code in (200, 202):
        return True, "Sent"

    try:
        err_msg = response.json().get("error", {}).get("message", response.text)
    except ValueError:
        err_msg = response.text or f"HTTP {response.status_code}"
    return False, err_msg


def _delete_draft(
    session: requests.Session, credential: InteractiveBrowserCredential, draft_url: str
) -> None:
    try:
        token = get_access_token(credential)
        session.delete(draft_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    except requests.RequestException:
        pass


def _put_chunk_with_retry(
    session: requests.Session,
    upload_url: str,
    chunk: bytes,
    offset: int,
    end: int,
    size: int,
) -> tuple[bool, str]:
    """PUT one chunk to an upload session, retrying transient failures.

    The upload URL carries its own authentication, so no Authorization header
    is sent here — adding one makes Graph reject the request.
    """
    headers = {
        "Content-Range": f"bytes {offset}-{end}/{size}",
        "Content-Length": str(len(chunk)),
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.put(upload_url, data=chunk, headers=headers, timeout=60)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                return False, f"Attachment upload failed: {exc}"
            time.sleep(min(DEFAULT_RETRY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_WAIT_SECONDS))
            continue

        if response.status_code in (200, 201, 202):
            return True, "Uploaded"

        if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
            return False, f"Attachment upload failed: HTTP {response.status_code}"

        backoff = min(DEFAULT_RETRY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_WAIT_SECONDS)
        time.sleep(parse_retry_after(response.headers.get("Retry-After"), backoff))

    return False, "Attachment upload failed after retries"


def _upload_large_attachment(
    session: requests.Session,
    credential: InteractiveBrowserCredential,
    draft_url: str,
    path: str,
) -> tuple[bool, str]:
    size = os.path.getsize(path)
    session_response, error = _request_with_retry(
        session,
        "POST",
        f"{draft_url}/attachments/createUploadSession",
        credential,
        json={
            "AttachmentItem": {
                "attachmentType": "file",
                "name": os.path.basename(path),
                "size": size,
            }
        },
        headers={"Content-Type": "application/json"},
    )
    if session_response is None:
        return False, error or "Failed to create upload session"
    if session_response.status_code not in (200, 201):
        return False, f"Failed to create upload session: HTTP {session_response.status_code}"

    upload_url = session_response.json()["uploadUrl"]

    with open(path, "rb") as f:
        offset = 0
        while offset < size:
            chunk = f.read(UPLOAD_CHUNK_SIZE)
            chunk_len = len(chunk)
            end = offset + chunk_len - 1

            ok, detail = _put_chunk_with_retry(session, upload_url, chunk, offset, end, size)
            if not ok:
                return False, detail
            offset += chunk_len

    return True, "Uploaded"


def send_via_graph_with_large_attachments(
    session: requests.Session,
    credential: InteractiveBrowserCredential,
    message: dict[str, Any],
    large_attachment_paths: list[str],
    config: CampaignConfig,
) -> tuple[bool, str]:

    endpoint = messages_endpoint(config)

    response, error = _request_with_retry(
        session,
        "POST",
        endpoint,
        credential,
        json=message,
        headers={"Content-Type": "application/json"},
    )
    if response is None:
        return False, error or "Failed to create draft"
    if response.status_code not in (200, 201):
        return False, f"Failed to create draft: HTTP {response.status_code} {response.text}"

    draft_id = response.json()["id"]
    draft_url = f"{endpoint}/{draft_id}"

    for path in large_attachment_paths:
        ok, detail = _upload_large_attachment(session, credential, draft_url, path)
        if not ok:
            _delete_draft(session, credential, draft_url)
            return False, detail

    send_response, send_error = _request_with_retry(
        session, "POST", f"{draft_url}/send", credential
    )
    if send_response is None:
        _delete_draft(session, credential, draft_url)
        return False, send_error or "Failed to send draft"
    if send_response.status_code not in (200, 202):
        _delete_draft(session, credential, draft_url)
        return False, f"Failed to send draft: HTTP {send_response.status_code} {send_response.text}"

    return True, "Sent"
