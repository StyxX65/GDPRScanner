# HTTPS via Zoraxy Reverse Proxy

Step-by-step guide for putting GDPRScanner behind [Zoraxy](https://github.com/tobychui/zoraxy) with a Let's Encrypt certificate, on a LAN-only deployment.

Why bother on an internal network:

- **Encryption in transit** — the scanner streams CPR numbers, document previews, and share links. Serving that over plain HTTP to DPO reviewers is itself a compliance finding.
- **Secure context** — the browser Clipboard API (share-link Copy buttons) only exists on HTTPS or localhost. Over plain HTTP the app falls back to a legacy copy mechanism.
- **A real hostname** — `https://gdprscanner.example.dk` instead of `http://10.x.x.x:5100` in share links, bookmarks, and emails.

This guide assumes Zoraxy runs **on the same host** as the scanner. If it runs elsewhere, replace `127.0.0.1:5100` with the scanner host's LAN IP and firewall port 5100 to the Zoraxy host only.

---

## 1. DNS record

Create an A-record for the hostname pointing at the server's **LAN IP**:

```
gdprscanner.example.dk    A    10.x.x.x
```

A public DNS record pointing at a private IP is fine — outsiders can resolve the name but cannot route to the address, which is exactly the "LAN-only" goal.

> **Consequence:** because the server is not reachable from the internet, Let's Encrypt's default HTTP-01 challenge cannot work. The certificate **must** be issued via the **DNS-01 challenge** (step 4). If you prefer not to publish the internal IP at all, use an internal/split-horizon DNS record instead — DNS-01 still works since it validates against the public DNS zone, not the server.

---

## 2. Install Zoraxy

```bash
mkdir -p /opt/zoraxy && cd /opt/zoraxy
wget -O zoraxy https://github.com/tobychui/zoraxy/releases/latest/download/zoraxy_linux_amd64
chmod +x zoraxy
```

`/etc/systemd/system/zoraxy.service`:

```ini
[Unit]
Description=Zoraxy reverse proxy
After=network.target

[Service]
WorkingDirectory=/opt/zoraxy
ExecStart=/opt/zoraxy/zoraxy
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now zoraxy
```

Open the management UI at `http://<server-ip>:8000` and create the admin account.

> Menu names below may differ slightly between Zoraxy versions — the concepts to look for are: ACME certificate with DNS challenge, host-based proxy rule, TLS on the incoming port.

---

## 3. Incoming port and TLS

In Zoraxy's global settings:

- Set the incoming proxy port to **443** and enable **TLS**.
- Enable **force-redirect port 80 → 443** so plain-HTTP visits upgrade automatically.

---

## 4. Certificate via ACME (DNS-01)

In **TLS / SSL Certificates → ACME**:

1. Enter the hostname (`gdprscanner.example.dk`).
2. Enable the **DNS challenge** and select the DNS provider that hosts your zone (Cloudflare, Simply.com, etc.).
3. Paste the provider's **API token/credentials** — created in the DNS provider's control panel.
4. Request the certificate. Zoraxy renews it automatically.

If your DNS host has no API, Zoraxy can generate a **self-signed certificate** as a fallback — it works, but every client machine must trust it manually. Getting a DNS API token is the better one-time investment.

---

## 5. Proxy rule

**HTTP Proxy → New Proxy Rule**:

| Field | Value |
|---|---|
| Matching hostname | `gdprscanner.example.dk` |
| Target | `127.0.0.1:5100` |
| TLS to target | Off (the scanner speaks plain HTTP locally) |

---

## 6. Close the side doors

**Bind the scanner to loopback** so only Zoraxy can reach Flask. Wherever the scanner is started (systemd unit or `start_gdpr.sh`), add:

```bash
--host 127.0.0.1
```

After a restart, `http://<server-ip>:5100` stops responding by design. The in-app self-update restart preserves the argument.

Optional hardening:

- Add a Zoraxy **Access Rule** whitelisting your LAN CIDR (e.g. `10.0.0.0/8`) on the proxy rule.
- Firewall the Zoraxy **management port 8000** to admin machines only.

---

## 7. Verify the scanner-specific behaviour

1. `https://gdprscanner.example.dk` loads with a valid padlock; `http://` redirects.
2. **Run a scan and watch result cards stream in live** — that is the Server-Sent Events connection (`/api/scan/stream`) passing through the proxy. If progress stalls while the scan log advances, look at proxy buffering/timeout settings.
3. Create a **share link** — it must start with `https://gdprscanner.example.dk/view?token=…`. The app uses the page origin automatically on HTTPS (the LAN-IP rewrite only applies when browsing at localhost). The Copy buttons now use the native Clipboard API.
4. **Settings → General → Software update → Check for updates** still works (outbound git fetch is unaffected by the proxy).

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Certificate request fails | HTTP-01 attempted against an unreachable host — make sure the **DNS challenge** is selected and the API credentials are for the zone's actual DNS host |
| Cards don't stream during scans | Proxy buffering the SSE response — check Zoraxy timeout/buffering settings for the rule |
| Share links still show the LAN IP | Page was loaded via the old `http://<ip>:5100` URL — use the HTTPS hostname; links follow the page origin |
| `http://<ip>:5100` still reachable | The `--host 127.0.0.1` flag is missing from the scanner's launch command |
