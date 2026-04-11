# Microsoft 365 Setup

Step-by-step guide for connecting GDPRScanner to Microsoft 365.

---

## 1. Register an app in Azure

Go to **Azure Portal → Microsoft Entra ID → App registrations → New registration**.

| Field | Value |
|---|---|
| Name | GDPRScanner (or any name) |
| Supported account types | Accounts in this organisational directory only |
| Redirect URI | Leave blank |

Click **Register**. Note the **Application (client) ID** and **Directory (tenant) ID** — you'll need both.

---

## 2. Choose an authentication mode

| Mode | How it works | When to use |
|---|---|---|
| **Application** | Client credentials — client ID + tenant ID + client secret. No user interaction. | Automated / scheduled scans, all-user scans |
| **Delegated** | OAuth device code flow — user signs in interactively. | Single-user scans, testing |

### Application mode — create a client secret

In your app registration: **Certificates & secrets → New client secret**.

Set an expiry (24 months recommended) and copy the **Value** immediately — it is only shown once.

### Delegated mode — no secret needed

The scanner will show a device code URL. Open it in a browser, sign in, and the scanner authenticates as that user.

---

## 3. Add API permissions

Go to **API permissions → Add a permission → Microsoft Graph**.

### Scan only

| Permission | Type |
|---|---|
| `Mail.Read` | Application or Delegated |
| `Files.Read.All` | Application or Delegated |
| `Sites.Read.All` | Application or Delegated |
| `ChannelMessage.Read.All` | Application |
| `Team.ReadBasic.All` | Application |
| `User.Read.All` | Application |

### Scan + Delete

Add these in addition to the read permissions above:

| Permission | Type |
|---|---|
| `Mail.ReadWrite` | Application or Delegated |
| `Files.ReadWrite.All` | Application or Delegated |
| `Sites.ReadWrite.All` | Application or Delegated |

### Email reports via Graph

If you want the scanner to send email reports via Microsoft 365 (not SMTP):

| Permission | Type |
|---|---|
| `Mail.Send` | Application or Delegated |

### Grant admin consent

All **Application** permissions require admin consent. Click **Grant admin consent for [your tenant]** at the top of the API permissions page. Without this, scans will fail with 403 errors.

---

## 4. Connect in GDPRScanner

Open GDPRScanner → **Source Management → Microsoft 365** tab.

| Field | Where to find it |
|---|---|
| Client ID | App registration → Overview → Application (client) ID |
| Tenant ID | App registration → Overview → Directory (tenant) ID |
| Client Secret | The value you copied in step 2 (Application mode only) |

Click **Connect**. In Application mode, the connection is immediate. In Delegated mode, a browser window opens for sign-in.

---

## 5. Verify

After connecting, the Sources panel shows:

- **Email** — Exchange mailboxes
- **OneDrive** — personal drives
- **SharePoint** — site file libraries
- **Teams** — Teams channel files

The Accounts panel lists all users in the tenant (Application mode) or just the signed-in user (Delegated mode).

---

## Notes on deletion

Emails deleted via the scanner are moved to **Deleted Items** — recoverable for 14–30 days depending on admin configuration. Files are sent to the **OneDrive/SharePoint recycle bin** — retained for 93 days across both recycle bin stages before permanent deletion. Nothing is permanently destroyed without a second manual step.

---

## Headless / scheduled mode

Headless mode uses Application auth only. Credentials are read in priority order:

1. `--settings FILE` — a JSON file you provide
2. Environment variables: `M365_CLIENT_ID`, `M365_TENANT_ID`, `M365_CLIENT_SECRET`

Example settings file:

```json
{
  "client_id":     "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "tenant_id":     "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_secret": "your-secret",
  "sources":       ["email", "onedrive"],
  "options": {
    "older_than_days": 365,
    "email_body":      true,
    "attachments":     true,
    "delta":           true
  }
}
```

Run:

```bash
python gdpr_scanner.py --headless --output ~/Reports/ --settings settings.json
```

See the full CLI flag reference in `README.md`.

---

## Role classification (staff / student)

GDPRScanner classifies users as **staff** or **student** based on their Microsoft 365 licence SKU. The mapping is in `classification/m365_skus.json`. If users appear as "other", open **Settings → SKU debug** to see which SKU IDs are assigned in your tenant and add any missing ones to `m365_skus.json`.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| 403 on scan start | Admin consent not granted, or wrong permissions added |
| `AADSTS7000215` | Invalid client secret — check it was copied correctly |
| No users listed | `User.Read.All` permission missing or not consented |
| Teams files not appearing | `ChannelMessage.Read.All` or `Team.ReadBasic.All` missing |
| Delta scan not working | Delta tokens require at least one full scan first |
