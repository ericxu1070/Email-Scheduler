# Email Scheduler — Apps Script setup

A Google Sheet + Apps Script project that ingests order/invoice CSVs and sends reminder emails on schedule. Runs on Google's infrastructure — your computer can be off.

## How it works

- A Google Sheet has three data tabs: `FamilyMeal`, `Wonton`, `DanceInvoice`, plus a `Config` tab with named ranges.
- Use the **Bentolicious** menu to import a CSV. Each row becomes a sheet row with a `status` column (`pending` / `sent` / `cancelled` / `error`).
- A single time-based trigger (`sendDue`) runs every 5 minutes, scans `FamilyMeal` and `Wonton` for `pending` rows whose `send_time` has passed, and sends them via `GmailApp` from the signed-in account.
- `DanceInvoice` rows send immediately on import (no scheduling).
- The Sheet itself is the dashboard. Select rows and use **Send selected rows now**, **Cancel selected rows**, or **Refresh send times for selected**.

## First-time setup (testing account)

1. **Create the Sheet**
   - Go to <https://sheets.new>. Rename it (e.g. "Email Scheduler").
   - Create four tabs with these exact names: `FamilyMeal`, `Wonton`, `DanceInvoice`, `Config`. (Or skip — the script will create the data tabs on first import. `Config` you must create manually.)

2. **Set up `Config` named ranges**
   - On the `Config` tab, in cell `A1` type `BENTO_PNG_FILE_ID`, in `B1` paste the Drive file ID of `bento.png` (see step 3).
   - In `A2` type `LEAD_HOURS`, in `B2` enter `4`.
   - In `A3` type `TICKER_MINUTES`, in `B3` enter `5`.
   - Select `B1`, then **Data → Named ranges**, name it `BENTO_PNG_FILE_ID`. Repeat for `B2` (`LEAD_HOURS`) and `B3` (`TICKER_MINUTES`).

3. **Upload `bento.png` to Drive**
   - Drag the `bento.png` from this repo into your Google Drive.
   - Open it, click the three-dot menu → **Share → Copy link**. The file ID is the long string between `/d/` and `/view` in the URL.
   - Paste it into the `BENTO_PNG_FILE_ID` cell.

4. **Add the script**
   - In the Sheet: **Extensions → Apps Script**. Delete the default `Code.gs` stub.
   - Create files matching this directory (Code.gs, Import.gs, Parsers.gs, Senders.gs, Templates.gs, Picker.html). Copy the contents of each in.
   - Click the gear → **Show "appsscript.json" manifest file in editor**. Replace its contents with `appsscript.json` from this directory.
   - Save.

5. **Authorize and install the trigger**
   - In the Apps Script editor, select `installTicker` from the function dropdown and click **Run**. Approve the OAuth scopes (Gmail send, Drive read, Spreadsheet, Script triggers).
   - Reload the Sheet. The **Bentolicious** menu should appear.

## (Optional) `clasp` workflow

[`clasp`](https://github.com/google/clasp) lets you push these local files to the Apps Script project from your terminal so you can version-control changes.

```bash
npm install -g @google/clasp
clasp login
cd apps-script
clasp clone <your-script-id>   # one-time; pulls the manifest the editor created
clasp push
```

`<your-script-id>` is in the Apps Script editor URL (`script.google.com/d/<ID>/edit`).

## Daily use

1. **Bentolicious → Import CSV → Family Meal…** (or Wonton / Dance Invoice)
2. Choose the CSV. Optionally fill in custom subject/body (use placeholders like `{full_name}`, `{item_name}`, `{pickup_time}`).
3. Click **Import**. Pending rows appear in the matching tab with their computed `send_time`.
4. Walk away. The 5-minute ticker handles the rest.

To act on a row before its scheduled time: select the row, then **Bentolicious → Send selected rows now** or **Cancel selected rows**.

## Cloning to production accounts

When you have access to `orderbentolicious@gmail.com` and `usa.tvda@gmail.com`:

1. Sign into the production account.
2. Repeat the **First-time setup** steps above. (Each Gmail account needs its own Sheet + script project — Apps Script triggers run as the project's owner.)
3. For the TVDA account, you only need the `DanceInvoice` tab — the FamilyMeal/Wonton tabs and the ticker can be skipped (dance invoices send immediately).
4. The local files in this directory work as-is in any account; nothing is hardcoded to a specific email address.

## Known limits / notes

- Free Gmail send quota is **500 recipients/day**. Workspace accounts get 2000.
- Ticker granularity is 5 minutes; an email may go out up to ~5 min after its `send_time`.
- The `Config` tab + named ranges must exist before running `installTicker` (the ticker reads `TICKER_MINUTES`).
- Editing a `pending` row's `pickup_time` in the sheet does NOT auto-recompute `send_time`. Use **Refresh send times for selected**.
- If the bento PNG fails to load (bad file ID, no Drive permission), reminders still send — just without the inline image.
