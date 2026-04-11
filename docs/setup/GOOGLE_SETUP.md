# Google Workspace Setup

Step-by-step guide for connecting GDPRScanner to Google Workspace via a service account.

GDPRScanner connects using a **service account** with **domain-wide delegation** — this allows it to scan all users' Gmail and Drive without requiring each user to sign in individually.

---

## 1. Create a Google Cloud project

Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (or use an existing one).

---

## 2. Enable the required APIs

In your project: **APIs & Services → Enable APIs and Services**. Enable:

- **Gmail API**
- **Google Drive API**
- **Admin SDK API**

---

## 3. Create a service account

Go to **IAM & Admin → Service accounts → Create service account**.

| Field | Value |
|---|---|
| Name | gdprscanner (or any name) |
| Description | GDPRScanner service account |

Click **Create and continue**. Skip the optional role and user access steps. Click **Done**.

### Create a key

Click on the service account → **Keys → Add key → Create new key → JSON**.

Download the JSON file. This is your service account key — treat it like a password.

---

## 4. Enable domain-wide delegation

Back on the service account page: **Show advanced settings → Domain-wide delegation → Enable**.

Note the **Client ID** (a long number) — you'll need it in the next step.

---

## 5. Authorise scopes in Google Admin Console

Go to [admin.google.com](https://admin.google.com) →
**Security → Access and data control → API controls → Manage domain-wide delegation → Add new**.

| Field | Value |
|---|---|
| Client ID | The numeric Client ID from the service account |
| OAuth scopes | See below |

Add all of these scopes (paste as a comma-separated list):

```
https://www.googleapis.com/auth/admin.directory.user.readonly,
https://www.googleapis.com/auth/gmail.readonly,
https://www.googleapis.com/auth/drive.readonly
```

Click **Authorise**. Changes can take a few minutes to propagate.

---

## 6. Connect in GDPRScanner

Open GDPRScanner → **Source Management → Google Workspace** tab.

1. **Upload service account key** — select the JSON file you downloaded in step 3
2. **Admin email** — enter the email address of a Google Workspace admin user in your domain (e.g. `admin@skolen.dk`). The service account impersonates this user to call the Admin Directory API.

Click **Connect**. If successful, the status dot turns green and shows the service account email.

---

## 7. User role classification

GDPRScanner classifies Google Workspace users as **staff** or **student** based on their **Organisational Unit (OU) path** in Google Admin.

The mapping is in `classification/google_ou_roles.json`. Edit it to match your school's OU structure — no code change required.

Default mapping:

| OU prefix | Role |
|---|---|
| `/Elever` | student |
| `/Personale` | staff |
| `/Admin` | staff |

To see your OU structure: **Google Admin → Directory → Administrer organisationsenheder**.

Example `classification/google_ou_roles.json` for a typical Danish school (Gudenaaskolen.dk structure):

```json
{
  "student_ou_prefixes": ["/Elever"],
  "staff_ou_prefixes":   ["/Personale", "/Admin"]
}
```

After editing the file, restart GDPRScanner — no rebuild required.

---

## 8. Verify

After connecting:

- **Sources panel** shows Gmail and Google Drive checkboxes
- **Accounts panel** shows all Google Workspace users with `GWS` badges
- Users are classified as Elev / Ansat based on their OU

Select one or more accounts, check Gmail and/or Google Drive, and click Scan.

---

## Notes on what is scanned

| Source | What is scanned |
|---|---|
| Gmail | Email bodies and attachments for all mail folders |
| Google Drive | My Drive files — Docs, Sheets, Slides are auto-exported to text for scanning |

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `unauthorized_client` on connect | Domain-wide delegation not enabled, or scopes not authorised in Admin Console |
| 0 users listed | `admin.directory.user.readonly` scope missing, or wrong admin email |
| Users show as "Anden" (other) | OU path not matched in `classification/google_ou_roles.json` — check OU paths in Google Admin and compare with the file |
| Gmail scan finds nothing | `gmail.readonly` scope not authorised |
| Drive scan finds nothing | `drive.readonly` scope not authorised |
| `RefreshError` on scan | Service account key expired or revoked — generate a new key |
