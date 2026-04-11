# Acronyms and Abbreviations

GDPR-related terms and abbreviations used throughout the GDPR Scanner project.

## GDPR / Legal

| Term | Full name | Meaning in context |
|---|---|---|
| GDPR | General Data Protection Regulation | The EU regulation (2016/679) — the primary legal framework the scanner addresses |
| CPR | Centrale Personregister | Danish national personal identification number (DDMMYY-XXXX) |
| PII | Personally Identifiable Information | Any data that can identify a person — names, addresses, phone numbers, IBANs etc. |
| NER | Named Entity Recognition | ML technique (via spaCy) used to detect names, addresses, and organisations in text |
| DPA | Data Protection Authority | Supervisory authority — in Denmark: Datatilsynet |
| DSR | Data Subject Request | A request from an individual to access, correct, or delete their data (Art. 15/17) |
| DPIA | Data Protection Impact Assessment | Risk assessment required before high-risk processing (Art. 35) — not yet in scanner |
| RoPA | Register of Processing Activities | The Article 30 register — what the Art.30 export produces |
| IBAN | International Bank Account Number | Financial identifier detected as sensitive PII |
| SKU | Stock Keeping Unit | In context: Microsoft license product code used to classify student vs staff accounts |

## GDPR Articles referenced in this project

| Article | Subject |
|---|---|
| Art. 5(1)(a) | Lawfulness, fairness, transparency |
| Art. 5(1)(b) | Purpose limitation |
| Art. 5(1)(c) | Data minimisation |
| Art. 5(1)(e) | Storage limitation — basis for retention enforcement |
| Art. 5(2) | Accountability — basis for the deletion audit log |
| Art. 8 | Conditions for child consent — age threshold |
| Art. 9 | Special categories of personal data (biometric, health, criminal etc.) |
| Art. 15 | Right of access — basis for data subject lookup |
| Art. 17 | Right to erasure ("right to be forgotten") |
| Art. 30 | Records of processing activities — basis for Article 30 export |
| Art. 35 | Data Protection Impact Assessment |
| Art. 44–46 | Transfers to third countries |
| Art. 89 | Archiving in the public interest — potential basis for retaining historical data |

## Danish law

| Term | Meaning |
|---|---|
| Databeskyttelsesloven | Danish Data Protection Act — supplements GDPR in Denmark |
| Databeskyttelsesloven §6 | Sets digital consent age at 15 — below this, parental consent required |
| Bogføringsloven | Danish Bookkeeping Act — requires accounting records for 5 years from end of financial year |
| Datatilsynet | Danish Data Protection Authority — the national supervisory body |

## Microsoft 365 / Technical

| Term | Full name | Meaning in context |
|---|---|---|
| M365 | Microsoft 365 | The cloud productivity suite (Exchange, OneDrive, SharePoint, Teams) |
| AAD / Entra | Azure Active Directory / Microsoft Entra ID | Microsoft's identity and access management service |
| MSAL | Microsoft Authentication Library | Library used for OAuth2 authentication against Azure AD |
| UPN | User Principal Name | Microsoft's unique user identifier — typically the user's email address |
| SKU | Stock Keeping Unit | Microsoft license product code (e.g. M365EDU_A3_STUDENT) |
| SPO | SharePoint Online | Microsoft's cloud document management platform |
| SSE | Server-Sent Events | HTTP streaming used to push scan results to the browser in real time |
| ORM | Object-Relational Mapping | Not used — the scanner uses raw SQL via sqlite3 |
