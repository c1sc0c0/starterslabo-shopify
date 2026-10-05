---
name: starterslabo-shopify
description: >-
  Sync Shopify (rebelchalk) paid B2C orders into mijn.starterslabo.be as
  monthly dagontvangsten plus a separate onkostennota for Shopify Payments
  fees. Use when the user mentions Shopify order, webshop sale, dagontvangsten
  from Shopify, or syncing shop sales into Starterslabo.
---

# Starterslabo ← Shopify sync

Unofficial. Not affiliated with Starterslabo or Shopify.

Pull paid **B2C** orders from **rebelchalk.myshopify.com**, then keep **one** month pair of portal drafts:

1. **Verkoop / dagontvangsten** — `SHOPIFY-DO-YYYYMM` — customer paid amount **incl. btw** (do not net the fee)
2. **Onkostennota** — `SHOPIFY-FEE-YYYYMM` — Shopify Payments **fee** as a separate cost

Re-run during the month: totals are rewritten on the same concepts. At month end, `--close` Verstuurs them. Booked invoices are never overwritten.

Never invent B2B named invoices from this script. Company-on-order rows are skipped.

## Mapping (from portal FAQ)

| Shopify | Starterslabo |
|---------|----------------|
| Paid B2C order, no company | Monthly **dagontvangsten** verkoopfactuur |
| `total_price` (incl. tax) | Line amount **tax-included** |
| Last day of month | Factuurdatum + vervaldatum if reeds betaald |
| Shopify Payments `fee` | **Onkostennota**, not a sales discount |
| Order export / this script’s boek | Bijlage (paper dagboek still required by FAQ) |

## Credentials

- **Shopify:** `SHOPIFY_REBELCHALK_TOKEN` or Keychain `security find-generic-password -s scout_shopify_rebelchalk -a api -w`. Never print the token.
- **Portal:** `STARTERSLABO_EMAIL` / `STARTERSLABO_PASSWORD` (skills `.env`). Never print the password.
- **DO identity** (your address on the dagontvangsten-factuur):

```bash
export STARTERSLABO_DO_NAME='DO Your Name'
export STARTERSLABO_DO_ADDRESS='…'
export STARTERSLABO_DO_CITY='…'
export STARTERSLABO_DO_POSTAL='…'
```

- **Paper PDF header:** `STARTERSLABO_BTW_NR` (default Starterslabo coöp BTW), `STARTERSLABO_DOSSIER_NR` (your dossiernr in brackets), and page **N°** from `STARTERSLABO_DO_BOOK_START` (YYYY-MM of page 1; one page per month).

## Workflow

```
Progress:
- [ ] 1. python scripts/sync_shopify.py --month YYYY-MM   (plan only)
- [ ] 2. Show plan (orders, € omzet, € fee). Confirm VAT rate and B2C vs B2B skips.
- [ ] 3. Copy paper PDF into physical ONTVANGSTEN book (see below)
- [ ] 4. --apply --dry-run  (fill portal, no save)  first time
- [ ] 5. --apply  during the month (upsert the same two CONCEPTS)
- [ ] 6. --close  last day / after the last order (upsert + Verstuur)
```

From the workspace (needs `reportlab` + `pypdf` for the paper PDF — `uv run --with reportlab --with pypdf` or `pip install -r scripts/requirements.txt`):

```bash
uv run --with reportlab --with pypdf \
  python .cursor/skills/starterslabo-shopify/scripts/sync_shopify.py --month 2026-09
python .cursor/skills/starterslabo-shopify/scripts/sync_shopify.py --month 2026-09 --apply
python .cursor/skills/starterslabo-shopify/scripts/sync_shopify.py --month 2026-09 --close
# Tune layout without hitting Shopify:
uv run --with reportlab --with pypdf \
  python .cursor/skills/starterslabo-shopify/scripts/sync_shopify.py --month 2026-09 --paper-pdf-only
```

`--apply` / `--close` call existing `skills/create_draft_invoice.py` and `skills/create_draft_expense.py` via `uv` (cwd `skills/`) with `--upsert` and stable keys. `--close` adds `--send`. `--apply --dry-run` fills without saving. If the month is already booked, the scripts exit without overwriting.

Default fee rekening: `612125` (software, website). Override with `STARTERSLABO_SHOPIFY_FEE_ACCOUNT` (or `610999` if Ruth prefers). Confirm with coach if unsure.

## Output

`shopify-sync/YYYY-MM/plan.json`, `dagontvangstenboek.txt`, `dagontvangstenboek-paper.pdf`, `shopify-fees.txt`. Do not commit those files or `.env`.

Portal `--attachment` stays on **`dagontvangstenboek.txt`** (per-order audit). The paper PDF is a **copy-aid** for the numbered physical book (FAQ: paper register still required).

## Manual paper book (month end)

1. Run sync for the month (writes txt + paper PDF from the same plan).
2. Open `dagontvangstenboek-paper.pdf` beside the physical **ONTVANGSTEN** page.
3. Copy row by row (days with sales; write `0,0` on quiet days if you fill every line). **N°** on the PDF is already filled (month index from `STARTERSLABO_DO_BOOK_START`).
4. Check footer totals against txt `Totaal incl. btw:` and the portal DO amount.
5. Attach **txt** (+ optional scan of the handwritten page) to the DO factuur as today.

Layout assets: `assets/dagontvangstenboek-template.pdf` (blank grid), `assets/paper_layout.json` (coordinates), `assets/dagontvangstenboek-voorbeeld.pdf` (filled FAQ example for visual reference).

Deps: `scripts/requirements.txt` (`reportlab`, `pypdf`).

## Do not

- Net Shopify fees off omzet
- Use a Shopify PDF as the customer’s legal factuur
- Treat the generated paper PDF as the legal dagontvangstenboek (final record = numbered paper book)
- Auto-Verstuur during the month (use `--close` only when the user wants to lock the month)
- Create a second invoice for the same month (upsert the existing `SHOPIFY-DO-YYYYMM` / `SHOPIFY-FEE-YYYYMM` drafts)
- Read `.env` unless the user said to use the local portal login
