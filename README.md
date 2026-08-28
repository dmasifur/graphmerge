# Graph Merge

Send personalized bulk email through your own Microsoft 365 mailbox using
Microsoft Graph — no passwords stored anywhere, authenticated via standard
Microsoft sign-in (OAuth).

## Features
- Mail merge from a CSV of recipients into an HTML or Word (.docx) template
  (Jinja2 `{{placeholders}}`)
- Send from your own mailbox or a shared mailbox you have Send As access to
- Optional CC, BCC, and file attachments per row — large attachments (over
  ~3MB) are sent via Microsoft Graph's upload-session flow automatically
- Built-in throttling/retry handling for Microsoft Graph rate limits and
  transient server errors
- Pre-send validation: flags recipient addresses that don't look valid and
  template placeholders with no matching CSV column
- Resumable campaigns: if a run is interrupted, re-running against the same
  CSV offers to skip recipients that were already sent successfully
- Test-send mode to preview against one recipient before a full run
- Downloadable send log

## Setup

### 1. Register an Azure AD app
1. Go to **Azure Portal → App registrations → New registration**
2. Choose **Public client** (no client secret needed)
3. Add a redirect URI for **Mobile and desktop applications** (e.g. `http://localhost`)
4. Under **API permissions**, add delegated permission **Mail.Send** (Microsoft Graph)
5. Grant admin consent if required by your tenant

### 2. Configure secrets
Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
your `client_id` and `tenant_id`.

### 3. Install and run
```bash
uv sync
uv run streamlit run app.py
```

## CSV format
Required: `To` or `email` column (case-insensitive). Optional: `CC`, `BCC`,
`Attachments` (semicolon-separated file paths), plus any custom columns to
use as `{{placeholders}}` in your subject and template.

## Word document templates
You can upload a `.docx` file instead of HTML — it's converted to HTML
automatically. Two things to know:
- Formatting is *approximated*, not pixel-perfect: fonts, exact spacing, and
  page layout are dropped in favor of clean HTML, since email clients
  ignore most of that anyway. Always check the preview before sending.
- Placeholders like `{{name}}` must be typed as plain, unbroken text. Word's
  autocorrect/spell-check can silently split a placeholder across multiple
  formatting runs, which breaks the merge — if a placeholder doesn't
  resolve, try retyping it with autocorrect off, or removing/reapplying
  formatting on that word.

## Resuming an interrupted campaign
Each send is logged locally, keyed by the exact content of the uploaded CSV
(a local `.graphmerge_logs/` file, not committed to git). If you re-upload
the same CSV after a run was interrupted, the app offers to skip recipients
that were already sent successfully. Editing the subject or template
between runs doesn't affect this — only changing the recipient data does.

## Notes
- Sending as a shared mailbox requires **Send As** or **Send on Behalf**
  permission on that mailbox for the signed-in account.
- Microsoft Graph enforces send-rate limits; the built-in delay and retry
  logic help avoid throttling on larger campaigns.
- Sign-in is cached locally (via your OS keychain), so you generally won't
  be prompted to sign in again on every run.

## License
MIT
