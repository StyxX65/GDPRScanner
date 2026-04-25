# Open Source Landscape — GDPR / PII Document Scanners

An overview of existing open source tools in the same space as GDPRScanner, and where the gaps are.

---

## Summary

No open source project covers the same combination of M365 + Google Workspace connectors, Danish CPR detection, and GDPR Article 30 reporting in a single web UI. The closest commercial equivalent is [PII Tools](https://pii-tools.com) (closed source, SaaS).

---

## Existing open source tools

### [Microsoft Presidio](https://github.com/microsoft/presidio)
A well-maintained PII detection *library* (not an application) from Microsoft. Supports custom recognisers — a CPR pattern could be added. Covers text, images, and structured data via NLP + regex pipelines. No M365/GWS connectors, no UI, no reports, no scheduling. You would have to build the entire scanning application around it. ~9k GitHub stars.

### [Octopii](https://github.com/redhuntlabs/Octopii)
Local filesystem / S3 / Apache open-directory scanner using OCR + NLP + regex. Detects passports, government IDs, emails, and addresses in image and document files. No cloud connectors, no CPR awareness, no web UI.

### [pdscan](https://github.com/ankane/pdscan) / [piicatcher](https://github.com/tokern/piicatcher)
CLI tools that scan *databases* and data warehouses for PII columns using column-name heuristics and NLP sampling. No file storage scanning, no email, no cloud connectors.

### "GDPR scanners" on GitHub
Projects such as [baudev/gdpr-checker-backend](https://github.com/baudev/gdpr-checker-backend), [dev4privacy/gdpr-analyzer](https://github.com/dev4privacy/gdpr-analyzer), [mammuth/gdpr-scanner](https://github.com/mammuth/gdpr-scanner), and [City-of-Helsinki/GDPR-compliance-scanner](https://github.com/City-of-Helsinki/GDPR-compliance-scanner) are all **website and cookie compliance** scanners. They check whether a domain sets tracking cookies without consent — a completely different problem.

### CPR libraries
Several small libraries exist for validating or generating Danish CPR numbers ([mathiasvr/danish-ssn](https://github.com/mathiasvr/danish-ssn), [anhoej/cprr](https://github.com/anhoej/cprr), [ekstroem/DKcpr](https://github.com/ekstroem/DKcpr)). None of them are document or cloud-storage scanners.

---

## Commercial products that do cover it

| Product | M365 | GWS | CPR | Article 30 | Open source |
|---|---|---|---|---|---|
| [PII Tools](https://pii-tools.com) | ✅ | ✅ | ❌ | ❌ | ❌ |
| BigID | ✅ | ✅ | ❌ | ❌ | ❌ |
| Varonis | ✅ | partial | ❌ | ❌ | ❌ |
| Spirion | ✅ | ❌ | ❌ | ❌ | ❌ |

PII Tools is the most direct commercial equivalent: Graph API + GWS service account connectors, document scanning, web UI. Closed source, SaaS pricing targeted at enterprise.

---

## Capability comparison

| Capability | GDPRScanner | Presidio | Octopii | Commercial |
|---|---|---|---|---|
| M365 (Exchange / OneDrive / SharePoint / Teams) | ✅ | ❌ | ❌ | ✅ |
| Google Workspace (Gmail / Drive) | ✅ | ❌ | ❌ | ✅ |
| Local / SMB / SFTP | ✅ | ❌ | partial | ✅ |
| Danish CPR with modulus-11 validation | ✅ | plugin only | ❌ | ❌ |
| Email address + phone number detection | ✅ | ✅ | ✅ | ✅ |
| GDPR Article 30 report generation | ✅ | ❌ | ❌ | partial |
| Disposition tagging + bulk deletion | ✅ | ❌ | ❌ | partial |
| Scheduled scans | ✅ | ❌ | ❌ | ✅ |
| Checkpoint / resume | ✅ | ❌ | ❌ | unknown |
| Read-only viewer / share links | ✅ | ❌ | ❌ | partial |
| Web UI for non-technical staff | ✅ | ❌ | ❌ | ✅ |
| Danish-language UI | ✅ | ❌ | ❌ | ❌ |
| Open source | ✅ | ✅ | ✅ | ❌ |

---

## What makes GDPRScanner unique

The combination of Danish CPR specificity (modulus-11 validation, date sanity checks), M365 + Google Workspace connectors in a single tool, and GDPR Article 30 output is the gap no open source project fills. The Danish public-sector target audience (schools, municipalities) also drives requirements — role classification (student/staff), Danish-language UI, municipal data retention rules — that no general-purpose PII tool addresses.
