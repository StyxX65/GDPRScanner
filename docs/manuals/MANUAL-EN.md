# GDPR Scanner — User Manual

Version 1.6.15

---

## Table of Contents

1. [What is GDPR Scanner?](#1-what-is-gdpr-scanner)
2. [The Interface at a Glance](#2-the-interface-at-a-glance)
3. [Connecting to Your Data Sources](#3-connecting-to-your-data-sources)
4. [Running a Scan](#4-running-a-scan)
5. [Understanding the Results](#5-understanding-the-results)
6. [Reviewing and Tagging Results](#6-reviewing-and-tagging-results)
7. [Deleting Items](#7-deleting-items)
8. [Profiles — Saving Your Scan Settings](#8-profiles--saving-your-scan-settings)
9. [Reports and Exports](#9-reports-and-exports)
10. [Sharing Results with a Reviewer](#10-sharing-results-with-a-reviewer)
11. [Scheduled Scans](#11-scheduled-scans)
12. [Email Reports](#12-email-reports)
13. [Database Backup and Restore](#13-database-backup-and-restore)
14. [Settings Reference](#14-settings-reference)
15. [Frequently Asked Questions](#15-frequently-asked-questions)

---

## 1. What is GDPR Scanner?

GDPR Scanner searches your organisation's digital data — emails, cloud files, shared drives, and local file servers — for personal data such as CPR numbers, names, addresses, phone numbers, and special-category data under GDPR Article 9.

When items are found, you can review them, decide what to do with each one (keep, delete, or note as out of scope), produce an Article 30 compliance report, and delete overdue data in bulk.

**What it scans:**
- Microsoft 365: Exchange email, OneDrive, SharePoint, Teams
- Google Workspace: Gmail, Google Drive
- Local and network file shares (including SMB/NAS drives)

**What it finds:**
- CPR numbers (Danish civil registration numbers)
- Phone numbers, email addresses, postal addresses
- Bank account and IBAN numbers
- Names and organisation names
- Photographs containing recognisable faces (optional)
- GPS location data embedded in image files

---

## 2. The Interface at a Glance

When you open the scanner, the screen is divided into three areas:

```
┌─────────────────┬──────────────────────────────────────────┐
│                 │  Top bar: Scan button, profiles, actions  │
│   Left sidebar  ├──────────────────────────────────────────┤
│                 │                                           │
│  - Sources      │         Results / scan progress           │
│  - Options      │                                           │
│  - Accounts     │                                           │
│  - Stats        ├──────────────────────────────────────────┤
│                 │               Activity log                │
└─────────────────┴──────────────────────────────────────────┘
```

**Left sidebar** — choose what to scan and how.  
**Top bar** — start a scan, select profiles, and access exports and settings.  
**Results area** — flagged items appear here as the scan runs.  
**Progress bar** — sits just above the activity log and shows which source is being scanned, who is being scanned, and how far along the scan is.  
**Activity log** — shows live status messages during scanning. Click the **▾** arrow in the log header to collapse or expand the panel. You can also filter the log to show only errors, copy all log text to the clipboard, and resize the panel by dragging the handle at its top edge.

### Dark / Light mode

Click the **🌙** button in the top-right corner to switch between dark and light mode. Your preference is remembered.

---

## 3. Connecting to Your Data Sources

Before you can scan, you need to connect to at least one data source. Click the **Sources** button in the top bar to open the Source Management panel.

### 3.1 Microsoft 365

The Microsoft 365 tab shows your current connection status. If you see a green dot and your account or tenant name, you are already connected.

**Sources you can enable or disable:**

| Toggle | What it scans |
|--------|---------------|
| Outlook | Exchange mailboxes (inbox, sent, all folders) |
| OneDrive | Each user's personal cloud storage |
| SharePoint | Team and project sites |
| Teams | Files shared in Teams channels |

Turn off any source you do not want to include. These settings are remembered.

### 3.2 Google Workspace

The Google Workspace tab lets you connect a Google Workspace (formerly G Suite) account via a service account, or a personal Google account via sign-in.

**Sources you can enable or disable:**

| Toggle | What it scans |
|--------|---------------|
| Gmail | All emails in each user's inbox and labels |
| Google Drive | All files owned by or shared with each user |

### 3.3 Local and Network File Shares

The **Filkilder** (File Sources) tab lists any local folders or network drives you have configured.

**To add a new file source:**
1. Enter a **Label** — a friendly name you will recognise (e.g. "Skolens Fællesmappe").
2. Enter the **Path**:
   - Local folder: `~/Documents` or `/Volumes/Share`
   - Network share: `//nas-server/shared` or `\\server\share`
3. If it is a network share, fill in the **SMB Host**, **Username**, and **Password** that appear automatically. The password is stored securely in your system keychain.
4. Click **Tilføj** (Add).

You can add as many file sources as you need. Each one will appear as a selectable source in the main sidebar when you are ready to scan.

---

## 4. Running a Scan

### 4.1 Select Your Sources

In the left sidebar under **Kilder** (Sources), tick the sources you want to include in this scan. You can mix M365, Google, and file sources in the same scan.

### 4.2 Choose Your Accounts

Under **Konti** (Accounts) the sidebar shows all users connected to your M365 and/or Google tenant.

- Use the **search box** to find specific people.
- Use the **Alle / Ansat / Elev** buttons to filter by role.
- Use the **Alle** and **Ingen** buttons to select or deselect everyone at once.
- Tick or untick individual names.

For file sources, accounts are not relevant — all files in the selected paths are scanned.

### 4.3 Configure Options

Under **Indstillinger** (Options) you can refine the scan:

**Date filter (Scan e-mails/filer fra)**  
Only scan items modified after a certain date. Quick presets — **1 år**, **2 år**, **5 år**, **10 år**, **Alle** — let you choose a window with one click. You can also pick a specific date with the date picker.

> Tip: Starting with "2 år" is a good first scan. You can always widen to "Alle" later.

**Email body** — scan the text content of emails. On by default.

**Attachments** — scan files attached to emails. On by default.

**Max attachment size** — skip attachments larger than this limit (default 20 MB). Increase it if you want to check large documents.

**Max emails per user** — stop after scanning this many emails per person (default 2,000). Increase if you need complete coverage.

### 4.4 Start the Scan

Click the blue **Scan** button in the top bar.

A progress bar appears showing:
- A coloured **source label** — **Outlook**, **OneDrive**, **SharePoint**, **Teams**, **Gmail**, **GDrive**, or **Local** — followed by the full name of the account currently being scanned
- A live count of items scanned and flagged
- An estimated time remaining

Results appear in the main area as they are found — you do not need to wait for the scan to finish before reviewing them.

To stop a scan, click **Stop**. A checkpoint is saved automatically so you can resume later.

### 4.5 Resuming an Interrupted Scan

If a scan was interrupted (by a stop, a crash, or closing the application), a yellow banner appears at the top of the results area:

> Previous scan interrupted — X scanned, Y found
> **▶ Genoptag** · Start fresh

Click **▶ Genoptag** to continue from where the scan left off. Click **Start fresh** to discard the checkpoint and begin again.

---

## 5. Understanding the Results

Each flagged item appears as a card. Here is what the badges and labels mean:

### Source badges

| Badge | Meaning |
|-------|---------|
| Outlook | Found in an Exchange mailbox |
| OneDrive | Found in a user's OneDrive |
| SharePoint | Found in a SharePoint site |
| Teams | Found in a Teams channel |
| Gmail | Found in a Gmail mailbox |
| Google Drive | Found in Google Drive |
| Local / Network | Found on a file share |

### Risk level

| Level | Meaning |
|-------|---------|
| HIGH | Multiple CPR numbers, special-category data, older than retention policy, or externally shared |
| MEDIUM | Single CPR with some sharing or contextual risk |
| LOW | Single CPR number, not shared, recent |

### Other badges

| Badge | Meaning |
|-------|---------|
| Number (e.g. **3**) | Number of CPR numbers found in this item |
| **Delt** (Shared) | The item has been shared with other users |
| **Ekstern** (External) | The item has been shared with someone outside your organisation |
| **Art. 9** | Special-category data detected (health, religion, biometric, etc.) |
| **N faces** | N recognisable faces detected in a photo |
| **GPS** | The file contains GPS location data in its metadata |

### Grid view vs. list view

The default **grid view** shows cards. Click **List** in the filter bar to switch to a compact table view with sortable columns. Click **Grid** to switch back.

### Filtering results

Use the filter bar above the results to narrow down what you see:

- **Search box** — search by name, subject, or path.
- **Source dropdown** — show only one source type.
- **Disposition dropdown** — show items by their review status.
- **Transfer dropdown** — filter by shared / external / all.
- **Risk dropdown** — show only Art. 9, photos, GPS, or high-risk items.
- **Role dropdown** — show only **Ansatte** (staff) or **Elever** (students). Also scopes exports: clicking **Excel** or **Art.30** while a role is selected produces a report containing only that group, with `_elever` or `_ansatte` appended to the filename.

---

## 6. Reviewing and Tagging Results

Click any result card to open the preview panel on the right side of the screen.

The preview shows:
- The item name or email subject
- The account (owner / sender)
- Source and modification date
- All CPR numbers found and their context
- Other personal data detected (phone, email address, IBAN, etc.)
- Sharing and external-access information

### Setting a disposition

Every item has a **Disposition** dropdown in the preview panel. Choose one of:

| Disposition | Use when… |
|-------------|-----------|
| Ikke gennemgået (Unreviewed) | Not yet assessed — the default |
| Opbevar — lovkrav | You must keep it by law |
| Opbevar — legitim interesse | You have a legitimate interest in keeping it |
| Opbevar — kontrakt | Required for a contract |
| Slet — planlagt | Marked for future deletion |
| Privat brug — uden for scope | Personal item, not in scope for GDPR processing |
| Slettet | Already deleted (set automatically when you delete an item) |

After choosing, click **Gem**. A small **✓ Gemt** confirmation appears.

### Finding all items for a specific person

Click **🔍** in the sidebar (under Stats) to open the **Data Subject Lookup**. Enter a CPR number and the scanner will find all flagged items containing that number. You can then delete all of them in one step — supporting the GDPR right to erasure (Article 17).

The CPR number is hashed before the search and is never stored in plaintext.

---

## 7. Deleting Items

### 7.1 Deleting a Single Item

With an item open in the preview panel, set its disposition to **Slet — planlagt**, then use the action button to delete it. The item moves to the Deleted Items folder (email) or recycle bin (files).

### 7.2 Bulk Delete

Click the **Delete** button in the filter bar to open the bulk delete modal.

1. **Set filters** to target the items you want to delete:
   - **Source type** — delete from one source or all.
   - **Min. CPR hits** — only delete items with at least this many CPR numbers.
   - **Older than date** — only delete items modified before a specific date.
   - Click **🗓 Filter overdue** to automatically fill in the date based on your retention policy.

2. The modal shows how many items match your filters.

3. Click the red **Delete matching items** button to proceed.

4. A progress bar shows deletions as they happen. Emails go to **Deleted Items**; files go to the **recycle bin**.

A full audit log of every deletion (what was deleted, when, and why) is included in the Article 30 report.

---

## 8. Profiles — Saving Your Scan Settings

A profile stores your chosen sources, accounts, scan options, and date settings so you can re-use them without reconfiguring every time.

### Saving a profile

Configure the sidebar exactly as you want it — including which M365 sources, Google sources, and local file sources are enabled, which accounts are selected, and all options — then click the **Save** button in the top bar. Enter a name and click OK. The profile is saved and selected immediately.

### Applying a profile

Click the profile dropdown in the top bar and select a profile. All sidebar settings — sources, accounts, options, and date filter — are loaded at once. The sidebar then shows your live state and you can adjust anything before scanning.

A **Clear** button appears next to the dropdown after you select a profile. Click it to clear the profile label without changing the sidebar settings. This is useful when you want to run a one-off scan without overwriting a saved profile.

### Managing profiles

Click **Profiles** to open the profile management panel. Here you can:

- **Edit** any profile — change its name, description, sources, accounts, or options.
- **Duplicate** a profile — useful as a starting point for a variation.
- **Delete** a profile.

> Note: Editing a profile does not affect scans already completed with that profile.

---

## 9. Reports and Exports

### 9.1 Excel Export

Click **Excel** in the filter bar to download the current results as an Excel workbook. The workbook contains:
- A summary tab with scan date, item counts, and source breakdown.
- A separate tab for each source type (Outlook, OneDrive, SharePoint, Teams, Gmail, Google Drive, Local, Network).
- Every flagged item, including source, account, CPR count, risk level, sharing status, and disposition.

The **Excel** and **Art.30** buttons are always available — even after restarting the application — and will export the results from the most recent completed scan session without requiring a new scan.

The Excel file is the main working document for your internal review process.

### 9.2 GDPR Article 30 Report (Word document)

Click **Art.30** in the filter bar to generate a Word document that satisfies the GDPR Article 30 requirement to maintain a record of processing activities.

The document includes:
- **Executive summary** — scan date, total items, CPR counts per source.
- **Data categories** — which types of personal data were found.
- **Data inventory** — the full list of flagged items.
- **Retention analysis** — items older than your retention policy, with a breakdown by source.
- **Special-category data (Art. 9)** — health, biometric, and other sensitive data found.
- **Photographs / biometric data** — if face scanning was enabled.
- **GPS data** — files with embedded location information.
- **Compliance trend** — flagged counts across your last 20 scans.
- **Deletion audit log** — a complete record of all deletions made through the scanner.
- **Methodology** — how the scan was performed and the legal basis for scanning.
- **Notes on student data** — guidance on parental consent requirements for children under 15.

---

## 10. Sharing Results with a Reviewer

You can give a DPO, school principal, or compliance coordinator read-only access to the results grid — including the ability to tag dispositions — without giving them access to scan controls, credentials, or settings.

### 10.1 Token links

Click the **🔗** button in the top-right of the top bar to open the Share panel.

1. Optionally enter a **Label** to identify who the link is for (e.g. "DPO review April 2026").
2. Choose a **Role scope** — **All roles**, **Ansatte** (staff only), or **Elever** (students only). A scoped link restricts the recipient to items belonging to that role group; they cannot see any other items, and the role filter is locked in their view.
3. Choose an **Expiry** — 7 days, 30 days, 90 days, 1 year, or Never.
4. Click **Create**. A unique link is generated: `http://host:5100/view?token=…`
5. Click **Copy** to copy the link to your clipboard, then send it to the reviewer.

The reviewer opens the link in any browser. They see the results grid (filtered to their permitted scope) and can tag dispositions but cannot start scans, change settings, view credentials, or delete items.

**Managing existing links**

The Share panel lists all active links. Each row shows the label, role badge (if scoped), expiry date, and when the link was last used. Click **Copy** to copy a link again, or **Revoke** to invalidate it immediately.

> **Tip:** In schools and municipalities it is common to have separate DPOs or compliance officers for staff data and student data. Create one scoped link for each — the student DPO will only ever see student items, and the staff DPO will only see staff items.

### 10.2 Viewer PIN

As an alternative to token links, you can set a numeric PIN (4–8 digits) in **Settings → Security → Viewer PIN**. Anyone who knows the PIN can open `http://host:5100/view` in a browser, enter the PIN, and access the read-only view for the duration of their browser session.

To set or change the PIN, enter the new PIN in the **New PIN** field and click **Save PIN**. To remove it, click **Clear PIN**.

> **Security note:** Token links are more secure than a PIN because each link can be individually revoked, has an expiry date, and can be role-scoped. Use the PIN option only for trusted internal reviewers on your local network who need access to all results.

### 10.3 What the reviewer can do

| Action | Allowed |
|--------|---------|
| Browse results grid | Yes |
| Filter and search results | Yes |
| Open item preview | Yes |
| Tag dispositions | Yes |
| Export to Excel | Yes |
| Export Article 30 report | Yes |
| Start or stop a scan | No |
| View or change credentials | No |
| Delete items | No |
| Access Settings | No |
| Create or revoke viewer links | No |
| See items outside their role scope | No |

---

## 11. Scheduled Scans

Go to **Settings → Planlægger** to configure automatic scans.

### Creating a scheduled scan

1. Click **+ Tilføj planlagt scanning** (+ Add scheduled scan).
2. Give the job a name.
3. Choose the frequency: **Dagligt**, **Ugentligt**, or **Månedligt**.
4. For weekly scans, choose the day of the week. For monthly, choose the day of the month.
5. Set the time the scan should run.
6. Choose a **Profile** — the scanner will use that profile's sources, accounts, and options.
7. Optionally enable:
   - **Send rapport automatisk** — email the Excel report to your configured recipients after each scan.
   - **Håndhæv opbevaringspolitik** — automatically delete items older than your retention policy after each scan.
8. Click **Gem** (Save).

The scheduler indicator in the top bar shows the date and time of the next scheduled scan ("Next: …").

### Viewing recent runs

The scheduler tab shows a history of recent runs, including start time, status, and the number of items flagged.

---

## 12. Email Reports

Go to **Settings → E-mailrapport** to configure email sending.

### Setting up SMTP

Fill in your outgoing mail server details:

| Field | Example |
|-------|---------|
| SMTP host | smtp.office365.com |
| Port | 587 |
| Username | scanner@skole.dk |
| Password | (your email password or app password) |
| From address | scanner@skole.dk |
| Recipients | dpo@skole.dk; it@skole.dk |

Click **Gem** to save, then click **Test** to send a test email and verify the configuration is working.

> If your account has MFA (two-factor authentication) enabled, you cannot use your regular password. You need to create an **App Password** in your account security settings:
> - **Microsoft personal account**: account.microsoft.com/security → App passwords
> - **Gmail**: myaccount.google.com → Security → 2-Step Verification → App passwords

### Sending a report manually

Click **Send nu** (Send now) to email the current Excel report immediately to all configured recipients.

---

## 13. Database Backup and Restore

All scan results, dispositions, and the deletion audit log are stored in a local database. It is good practice to take regular backups.

Go to **Settings → Database**.

### Backup (Export)

Click **Export** to create a `.zip` backup of your database. Save it to a safe location.

### Restore (Import)

Click **Import** to restore from a backup. Two modes are available:

| Mode | When to use |
|------|-------------|
| Merge (safe) | Add dispositions and deletion log from the backup to your existing data. Use this to consolidate data from multiple installations. |
| Replace (full restore) | Erase everything and restore the backup completely. Use this to move to a new machine or recover from data loss. Requires Admin PIN confirmation. |

### Reset database

Click **Reset DB** to wipe all scan data, dispositions, and deletion log. This is irreversible. If an Admin PIN is set, you must enter it to proceed.

---

## 14. Settings Reference

### General tab

| Setting | Description |
|---------|-------------|
| Theme | Dark or light mode |

### Security tab

| Setting | Description |
|---------|-------------|
| Admin PIN | Optional PIN that protects destructive actions (database reset, replace import) |
| Viewer PIN | Optional 4–8 digit PIN that lets anyone open `/view` in a browser for read-only access to results without a token link |

### Advanced scan options

These options are in the left sidebar under **Indstillinger**:

**Delta scanning** — after your first full scan, enable this to scan only items that have changed since the last scan. Much faster for routine checks. A "Clear tokens" button forces the next scan to be a full scan.

**Scan photos for faces** — slower scan that detects photographs containing recognisable human faces. Flags them as Article 9 biometric data. Recommended for schools storing student photos.

**Ignore GPS in images** — when enabled, images whose only PII signal is an embedded GPS location are not flagged. Useful when scanning student accounts: smartphones embed GPS coordinates in every photo taken with the camera app, which would otherwise generate large numbers of flags that are low-priority for a school context. If an image is already flagged for another reason (faces, EXIF author field), the GPS coordinate is still shown in the detail card.

**Min. CPR count per file** — only flag a file if it contains at least this many *distinct* CPR numbers. The default is 1 (current behaviour). Setting it to 2 avoids false positives in student scans: a student's own consent form or registration document typically contains only their own CPR number, while a class list or grade sheet containing multiple students' CPRs will still be reported.

**Retention policy** — when enabled, marks items older than the specified number of years as overdue. The fiscal year end setting determines how the cutoff date is calculated:

| Option | Cutoff date calculation |
|--------|------------------------|
| Rolling (fra i dag) | Today minus N years |
| 31 dec (Bogføringsloven) | Last 31 December minus N years |
| 30 jun / 31 mar | Last occurrence of that date minus N years |

---

## 15. Frequently Asked Questions

**Does the scanner store CPR numbers?**  
No. CPR numbers found during a scan are stored only as a count (e.g. "3 CPR numbers found") and as a SHA-256 hash used for the Data Subject Lookup. The actual number is never written to the database.

**What happens when I delete items through the scanner?**  
Emails are moved to the user's **Deleted Items** folder in Exchange — they are not permanently deleted and can be recovered by the user or an administrator. Files are moved to the **recycle bin** of the relevant service (OneDrive, SharePoint, file system). A permanent deletion requires a second action by the user or admin.

**Can I scan without connecting to Microsoft 365?**  
Yes. You can scan local and SMB file shares without any M365 or Google connection. Open **Sources**, go to the **Filkilder** tab, and add your file paths.

**What is delta scanning and when should I use it?**  
Delta scanning uses Microsoft Graph change tokens to fetch only items modified since the last scan. It is ideal for regular (e.g. weekly) compliance checks after you have done a full baseline scan. Enable it in the Options section of the sidebar.

**The scan stopped — can I continue where it left off?**  
Yes. When you restart the scan, a yellow banner will offer to resume from the checkpoint. Click **▶ Genoptag** to continue. If you prefer to start over, click **Start fresh**.

**How do I prove compliance if we are audited?**  
Use the **Art.30** button to export the Article 30 report. It is a Word document covering your data inventory, retention analysis, deletion log, and methodology — exactly what a supervisory authority (Datatilsynet) typically requests.

**What does the "Elev / Ansat" filter do?**  
The scanner classifies users as staff (Ansat) or students (Elev) based on their Microsoft 365 licence type or Google Workspace organisational unit. You can use this filter in the accounts list to restrict a scan to only staff, only students, or a specific individual. This is useful because the rules for processing student data — especially for children under 15 — differ from staff data under Databeskyttelsesloven.

**How do I add an account that is not in the list?**  
In the accounts section of the sidebar, there is an **+ Tilføj konto manuelt** (Add account manually) field. Enter the email address or UPN and it will be added to the current session's account list.

**Is the scanner running? I cannot see a progress bar.**  
Check the activity log at the bottom of the screen. If a scan is running it will show messages there. If you see nothing, the scan may have completed or not started. Also check that you have at least one source ticked and at least one account selected.

**Can a reviewer tag dispositions without access to the scan controls?**  
Yes. Use the **🔗 Share** button to create a read-only viewer link or set a Viewer PIN in Settings → Security. The reviewer opens the link in their browser and can browse results and tag dispositions without seeing credentials, sources, or scan buttons. See section 10 for details.

---

*GDPR Scanner v1.6.14 — for technical setup and configuration see README.md*
