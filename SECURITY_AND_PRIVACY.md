# Security and privacy

This document describes how dicom-sr-to-pdf handles patient data, for organizations assessing it under HIPAA, GDPR or similar rules. It describes the software's technical behaviour. It is not legal advice, and it does not by itself make any organization compliant.

## Summary

- **No patient data ever leaves the user's device.** Both the web app and the command-line tool convert files locally.
- **No server receives, stores or logs files or PDFs.** The web app is static files on GitHub Pages; the command-line tool makes no network connections.
- **The browser enforces this.** The web app's Content-Security-Policy forbids the page, and the code that converts files, from contacting any server other than the site itself.
- **All code is served from the site itself**, and every third-party file is checked against a recorded SHA-256 fingerprint before publication.
- **No accounts, cookies, analytics, trackers or third-party scripts.**

## HIPAA: what applies

HIPAA obligations fall on *covered entities* (providers, plans, clearinghouses) and their *business associates* (vendors that create, receive, maintain or transmit PHI on their behalf). Software isn't "HIPAA certified"; organizations use it in a compliant way.

Because the tool never receives, stores or transmits PHI, its author and its host (GitHub Pages) **do not have access to PHI**, so they are not acting as business associates for it, and a business associate agreement is not applicable. The organization using the tool remains responsible for its own safeguards (see [Your responsibilities](#your-responsibilities)). Confirm this assessment with your privacy or compliance officer.

## Data flow

### Web app (`https://haani76.github.io/dicom-sr-to-pdf/`)

```
User's device                                                  Internet
┌─────────────────────────────────────────────┐
│ Browser tab                                 │   page code, converter runtime
│  ┌──────────────┐  file bytes  ┌──────────┐ │ ◄────────────────────────── this site only
│  │ app.js (UI)  │ ───────────► │ worker   │ │   (no file data is ever sent)
│  │ file picker  │ ◄─────────── │ Python   │ │
│  └──────────────┘    PDF       │ converter│ │   all other destinations:
│        │                       └──────────┘ │ ──X──  blocked by the browser (CSP)
│        ▼                                    │
│  preview / download (stays on device)       │
└─────────────────────────────────────────────┘
```

1. The browser downloads the page and the converter (HTML, JavaScript, the Pyodide Python runtime and Python packages) **from the site itself**. These downloads contain no patient data.
2. The user selects SR files. The browser reads them **into memory** and passes them to a background worker in the same tab.
3. The worker runs the Python converter and returns the PDF to the page, still in memory.
4. The user previews it (held as an in-memory `blob:` URL) and/or downloads it to their device.
5. **Remove** / **Remove all** delete the file's entry, its PDF and its preview from the page. Closing the tab discards everything. Nothing is written to cookies, local storage, IndexedDB or any server.

### Command-line tool

Reads SR files from disk and writes PDFs to disk. It makes no network connections. Only installation (`pip install`) uses the network, and that's to download the code, never data.

## Technical safeguards (web app)

| Safeguard | What it does |
|---|---|
| **Client-side processing** | Conversion runs in the browser, so there's no server-side component to breach |
| **Content-Security-Policy** (`connect-src 'self'`, `default-src 'none'`, `form-action 'none'`, ...) | The browser refuses any request, form submission or image load to another server. Even altered or malicious code in the page couldn't send data out |
| **Worker inherits the policy** | The converter runs in a worker created from a `blob:` URL, which inherits the page's policy, so the converter is restricted too |
| **Self-hosted dependencies** | The Python runtime and all packages are served from the site, not from public CDNs at run time |
| **Hash-pinned dependencies** | `web/vendor-lock.json` records the SHA-256 of every third-party file. `web/build_site.py` refuses to publish if any file differs |
| **No inline scripts** | The policy forbids inline JavaScript, which blocks a common injection technique |
| **No persistence** | No cookies, storage, service workers or logs |
| **Tested** | During development, requests to an outside server from the page, from a worker and via an image tag were all confirmed blocked |

What this cannot protect against: a compromised user device or browser extension (which can read anything on screen), or someone with write access to this repository publishing altered code. Protect repository access with two-factor authentication, and review changes before merging. Organizations that need full control can host their own copy, including on an internal network (see the README).

## Versions and rollback

Every release is tagged (`v1.0.0`, `v1.1.0`, ...). The live site can be switched to any tagged version from GitHub Actions ("Deploy web app" → "Run workflow" → enter the tag), and the command-line tool can be installed at a specific tag. This supports change control: you can validate a version, keep using it, and roll back if needed.

## Your responsibilities

When your organization uses this tool, your existing safeguards still apply:

- **Devices**: use the tool on managed devices with full-disk encryption, screen locks and up-to-date browsers.
- **Downloaded PDFs are PHI.** Store and share them only through approved, secure channels (not personal email or unencrypted USB drives), and dispose of them per your retention policy.
- **Browser hygiene**: avoid untrusted browser extensions on machines used with PHI. Close the tab, or use **Remove all**, when finished on a shared computer.
- **Risk analysis**: list the tool in your HIPAA risk analysis and asset inventory, and note the version in use.
- **Training**: make sure staff know the PDF is a rendering of the SR, not a signed clinical report.

## Reporting a security issue

Please don't open a public issue with patient data in it. Report security problems privately through GitHub's *Security → Report a vulnerability* on this repository, with an anonymised example if you can.
