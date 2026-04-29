# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Google Apps Script project (under `apps-script/`) bound to a Google Sheet. Ingests order/invoice CSVs, schedules reminder emails, and sends them via the signed-in account's Gmail. Runs on Google's infrastructure — no server, no SMTP, no hosting. The Sheet is also the dashboard.

There is **no Python/Flask code** in this repo anymore. An earlier iteration was a Flask app deployed to Fly.io; it was deleted because Fly's `auto_stop_machines` made the in-memory APScheduler unreliable. See `apps-script/README.md` for the user-facing setup story.

## Architecture

### Two-account split

Production will run as **two separate Apps Script projects**, one per Gmail account (Bentolicious + TVDA). The same files in `apps-script/` work in either — nothing is hardcoded to a sender address. For testing right now there is a single project in the user's personal Gmail (`ericxu1070@gmail.com`).

### Files (`apps-script/`)

| File | Role |
| --- | --- |
| `appsscript.json` | Manifest. Timezone `America/Los_Angeles`. Scopes: Gmail send, Drive read, Spreadsheet, Script triggers, Container UI. |
| `Code.gs` | `onOpen` menu, `installTicker` / `removeTicker`, **`sendDue` (the only triggered function)**, selection actions (`sendSelectedNow`, `cancelSelected`, `refreshSelected`), `readConfig`. |
| `Import.gs` | CSV column mappings (one per format), sheet schemas (`SHEET_HEADERS`), `showImportDialog` + `importRows` server endpoint, `_ensureSheet`, `_appendRow`. |
| `Senders.gs` | `sendOrderReminder` (Bentolicious formats, with inline `bento.png`), `sendDanceInvoice` (TVDA, plain text), `loadBentoBlob`. |
| `Templates.gs` | Default subject/body strings per format, `formatTemplate` (`{placeholder}` substitution), `buildEmailContext` (maps row → context dict). |
| `Parsers.gs` | `parsePickupTime`, `parseDateFromItemName`, `formatPickupTime`, `computeSendTime`, `TZ` constant. |
| `Picker.html` | Modal dialog with `<input type="file">` + custom subject/body fields. Reads CSV via FileReader, calls `importRows` over `google.script.run`. |
| `README.md` | User-facing setup steps for cloning into a Google account. |

### Sheet contract

The script does **not** auto-create the `Config` tab — it reads named ranges (`BENTO_PNG_FILE_ID`, `LEAD_HOURS`, `TICKER_MINUTES`) the user must define manually. Data tabs (`FamilyMeal`, `Wonton`, `DanceInvoice`) are auto-created on first import using `SHEET_HEADERS` from `Import.gs`. Header row is frozen.

`SHEET_HEADERS` is the single source of truth for column order — `Code.gs` and `Import.gs` look up columns by `headers.indexOf(name)`, so reordering or renaming a header in one place requires updating that array.

### Scheduling model

Apps Script has a hard limit of ~20 installable triggers per script per user, so per-row triggers are not viable. Instead, a single time-based trigger (`sendDue`, default every 5 min, configurable via `TICKER_MINUTES`) scans `FamilyMeal` and `Wonton` for rows where `status === 'pending'` AND `send_time <= now`, sends them, and updates `status` to `sent` or `error`.

`DanceInvoice` rows bypass this entirely — they send synchronously inside `importRows` and are written with `status = 'sent'`. The `sendDue` loop never touches them (`BENTO_FORMATS` in `Code.gs` excludes `dance_invoice`).

`status` lifecycle: `pending` → `sent` (success) | `error` (exception thrown by `GmailApp`) | `cancelled` (user clicked Cancel selected). Once non-pending, the row is inert.

### Time handling

All times are anchored to `America/Los_Angeles` via the project manifest. `Parsers.gs` uses `Utilities.parseDate(iso, TZ, 'yyyy-MM-dd HH:mm:ss')` to construct the pickup `Date`, then subtracts `LEAD_HOURS * 3600 * 1000` ms. Don't introduce raw `new Date(year, month, day, ...)` constructors — they use the JS engine's local timezone, not the project timezone, and will drift.

`parsePickupTime` ports the Python regex behavior from the old Flask app: it strips `Dinner:`/`Lunch:` prefixes (Wonton only), splits time ranges on `-` (takes the first half), and normalizes `7:32AM` → `7:32 AM` before matching `h:mm a` / `h a`. `parseDateFromItemName` regex-extracts `M/D` or `M/D/YYYY` from the item name and falls back to today.

## Conventions and gotchas

- **GmailApp vs MailApp**: use `GmailApp.sendEmail` so emails come from the signed-in account's actual Gmail (the whole point of this rewrite). `MailApp` would also work but tags messages differently and shows "via" headers more aggressively.
- **Inline image**: Bentolicious reminders attach `bento.png` via `options.inlineImages = { bento: bentoBlob }` and reference it in `htmlBody` as `<img src="cid:bento">`. The blob is loaded once per `sendDue()` and reused. If `BENTO_PNG_FILE_ID` is missing or unreadable, sends still succeed without the image.
- **No retries**: a failed send sets `status='error'` and writes the exception to the `error` column. The user re-runs "Send selected rows now" after fixing whatever was wrong (bad email, quota, etc.). Don't add silent retry loops.
- **Manifest scopes**: adding a new Apps Script API requires updating `appsscript.json`. The user will be re-prompted for OAuth consent on the next run.
- **Quota**: Free Gmail = 500 recipients/day. Workspace = 2000.
- **clasp**: The repo is structured for clasp but `.clasp.json` (which holds the script ID) is gitignored — each Apps Script project has its own ID. The user runs `clasp clone <id>` per account on their machine.

## Common operations

- **Add a new CSV format**: extend `COLUMN_MAPPINGS`, `SHEET_HEADERS`, and `SHEET_NAMES` in `Import.gs`; add an entry to `DEFAULT_SUBJECTS`/`DEFAULT_BODIES` in `Templates.gs`; either include it in `BENTO_FORMATS` (in `Code.gs`) for ticker-based sending or branch it in `importRows` for synchronous sending.
- **Change the lead time**: edit the `LEAD_HOURS` named range in the Sheet (no code change). Existing pending rows keep their old `send_time` until the user runs **Refresh send times for selected**.
- **Change ticker frequency**: edit `TICKER_MINUTES` in the Sheet, then run **Remove ticker** + **Install 5-minute ticker** from the menu.

## Verification

There is no test framework (Apps Script doesn't have a first-class one). To verify changes, push via clasp (or paste in the editor), then:

1. Import a small CSV with a row whose `send_time` is ~10 min in the future.
2. Confirm the row shows `pending` with the right `send_time`.
3. Wait for the next ticker tick; confirm `status` flips to `sent` and the email arrives.
4. For Bentolicious formats, confirm the inline `bento.png` renders.
5. For `dance_invoice`, confirm it sends immediately on import.

There is no equivalent of the old `/scheduled` web route — the Sheet rows are the dashboard.
