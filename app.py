import io
import time
from datetime import UTC, datetime
from typing import Any, cast

import pandas as pd
import requests
import streamlit as st

from campaign_log import CampaignLogEntry, append_entries, clear_log, csv_hash, sent_row_indices
from mailer import (
    CampaignConfig,
    SendResult,
    build_message,
    find_missing_placeholders,
    get_access_token,
    get_credential,
    get_field,
    load_template,
    normalize_columns,
    render_row,
    render_text,
    send_via_graph,
    send_via_graph_with_large_attachments,
    validate_attachments,
    validate_recipients,
)

st.set_page_config(page_title="M365 Bulk Mail Merge", page_icon="📧", layout="centered")

st.title("📧 M365 Bulk Mail Merge")
st.caption("Send personalized bulk email through your own Microsoft 365 mailbox")

try:
    CLIENT_ID = st.secrets["azure"]["client_id"]
    TENANT_ID = st.secrets["azure"]["tenant_id"]
except Exception:
    st.error(
        "**Configuration missing.** Create `.streamlit/secrets.toml` with your "
        "Azure app registration's `client_id` and `tenant_id`. See the README "
        "for setup instructions."
    )
    st.stop()

with st.expander("ℹ️First time here? Setup requirements"):
    st.markdown(
        """
        This app needs an **Azure AD app registration** (public client) with:
        - Redirect URI configured for interactive/desktop auth
        - Delegated permission: `Mail.Send`
        - Admin consent granted (or user consent allowed) for your tenant

        See `README.md` for step-by-step instructions.
        """
    )


st.subheader("1. Choose sender")
sender_choice = st.radio("Send from:", ["My mailbox", "A shared mailbox"], horizontal=True)
shared_mailbox = ""
sending_from_shared = sender_choice == "A shared mailbox"
if sending_from_shared:
    placeholder = "marketing@yourcompany.com"
    shared_mailbox = st.text_input("Shared mailbox address", placeholder=placeholder).strip()
    st.info("You need **Send As** or **Send on Behalf** permission on this mailbox.", icon="⚠️")
    if not shared_mailbox:
        st.warning("Enter the shared mailbox address before sending.")


st.subheader("2. Upload your data")
col1, col2 = st.columns(2)
with col1:
    csv_file = st.file_uploader("Recipient CSV", type=["csv"])
with col2:
    html_template_file = st.file_uploader(
        "Email template", type=["html", "txt", "docx"],
        help="Plain HTML/text, or a Microsoft Word document.",
    )

if not (csv_file and html_template_file):
    st.stop()

raw_csv_bytes = csv_file.getvalue()
try:
    df = pd.read_csv(io.BytesIO(raw_csv_bytes)).fillna("")
except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
    st.error(f"Couldn't read that CSV — is it a valid comma-separated file? ({exc})")
    st.stop()

if df.empty:
    st.error("That CSV has no data rows — it needs a header row plus at least one recipient.")
    st.stop()

df_columns = set(df.columns)
col_map = normalize_columns(df_columns)

if "to" not in col_map and "email" not in col_map:
    st.error("Your CSV needs a `To` or `email` column to know who to send to.")
    st.stop()

st.write(f"**{len(df)} recipients loaded.** Preview:")
st.dataframe(df.head(3), width="stretch")

template_filename = html_template_file.name
raw_template = load_template(template_filename, html_template_file.getvalue())
if template_filename.lower().endswith(".docx"):
    st.caption("Word formatting is approximated — check the preview below before sending.")

st.subheader("3. Compose")
email_subject = st.text_input("Subject line", value="Hello {{name}}, an update for you")

st.subheader("Validation")
validation_problems: list[str] = []
missing_vars = find_missing_placeholders(email_subject, df_columns) | find_missing_placeholders(
    raw_template, df_columns
)
if missing_vars:
    cols = ", ".join(sorted(missing_vars))
    validation_problems.append(f"Template references column(s) not found in the CSV: {cols}")
validation_problems.extend(validate_recipients(df, col_map))
validation_problems.extend(validate_attachments(df, col_map))

if validation_problems:
    st.warning("Found potential issues — review before sending:\n\n" + "\n".join(
        f"- {p}" for p in validation_problems
    ))
else:
    st.success("No validation issues found.")

with st.expander("👁️ Preview first recipient's email"):
    first_row: dict[str, Any] = {str(k): v for k, v in df.iloc[0].to_dict().items()}
    try:
        st.markdown(f"**Subject:** {render_text(email_subject, first_row)}")
        with st.container(height=300, border=True):
            st.html(render_row(raw_template, first_row))
    except Exception as exc:
        st.warning(f"Couldn't render preview — check your template placeholders. ({exc})")

st.subheader("4. Send")

campaign_hash = csv_hash(raw_csv_bytes)
already_sent = sent_row_indices(campaign_hash)
resume = False
if already_sent:
    st.info(
        f"{len(already_sent)} of {len(df)} recipients were already sent successfully in a "
        "previous run of this exact CSV."
    )
    resume = st.checkbox("Skip already-sent recipients (resume)", value=True)
    if st.button("Clear resume history for this CSV"):
        clear_log(campaign_hash)
        st.rerun()

test_mode = st.checkbox("Send a test to only the first recipient", value=True)
delay_seconds = st.slider("Delay between sends (seconds)", 0.0, 2.0, 0.2, 0.1,
                           help="A small delay is polite to the API and reduces throttling.")

confirmed = st.checkbox("I've reviewed the preview and recipient list above")

missing_shared_mailbox = sending_from_shared and not shared_mailbox
if st.button(
    "🚀 Sign in & send", type="primary", disabled=not confirmed or missing_shared_mailbox
):
    config = CampaignConfig(
        client_id=CLIENT_ID,
        tenant_id=TENANT_ID,
        sender_type="shared" if sending_from_shared else "personal",
        shared_mailbox=shared_mailbox or None,
        delay_seconds=delay_seconds,
    )

    rows = df.iloc[:1] if test_mode else df
    if resume and not test_mode:
        rows = rows[~rows.index.isin(already_sent)]

    results: list[SendResult] = []

    with st.status("Running campaign...", expanded=True) as status:
        st.write("🔐 Signing in to Microsoft...")
        credential = get_credential(config.client_id, config.tenant_id)
        get_access_token(credential)  # triggers sign-in up front
        st.write("✅ Signed in. Sending emails...")

        progress = st.progress(0.0)
        session = requests.Session()

        for i, (row_index, row) in enumerate(rows.iterrows()):
            row_dict: dict[str, Any] = {str(k): v for k, v in row.to_dict().items()}
            recipient = get_field(row_dict, col_map, "To", "email") or "(unknown)"
            try:
                message, large_paths = build_message(row_dict, email_subject, raw_template, col_map)
                if large_paths:
                    success, detail = send_via_graph_with_large_attachments(
                        session, credential, message, large_paths, config
                    )
                else:
                    success, detail = send_via_graph(session, credential, message, config)
            except Exception as exc:
                success, detail = False, str(exc)

            results.append(
                SendResult(row=i + 1, recipient=recipient, success=success, detail=detail)
            )

            append_entries(
                campaign_hash,
                [
                    CampaignLogEntry(
                        row_index=cast(int, row_index),
                        recipient=str(recipient),
                        success=success,
                        detail=detail,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                ],
            )
            progress.progress((i + 1) / len(rows))

            if config.delay_seconds:
                time.sleep(config.delay_seconds)

        status.update(label="Done!", state="complete", expanded=False)

    success_count = sum(r.success for r in results)
    fail_count = len(results) - success_count

    m1, m2 = st.columns(2)
    m1.metric("Sent", success_count)
    m2.metric("Failed", fail_count)

    if test_mode:
        st.info(
            "This was a test send to one recipient. Uncheck **Send a test** to run "
            "the full campaign."
        )

    log_df = pd.DataFrame([r.__dict__ for r in results])
    st.dataframe(log_df, width="stretch")
    st.download_button(
        "⬇️ Download send log (CSV)",
        log_df.to_csv(index=False).encode("utf-8"),
        file_name="send_log.csv",
        mime="text/csv",
    )
