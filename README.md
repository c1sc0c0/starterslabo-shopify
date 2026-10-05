# Starters Labo — Shopify → dagontvangsten skill

Unofficial [Cursor](https://cursor.com) / [Claude Code](https://code.claude.com) skill that pulls paid **B2C** Shopify orders and prepares monthly **dagontvangsten** for [mijn.starterslabo.be](https://mijn.starterslabo.be):

1. **Verkoop / dagontvangsten** draft (`SHOPIFY-DO-YYYYMM`) — omzet incl. btw  
2. **Onkostennota** draft (`SHOPIFY-FEE-YYYYMM`) — Shopify Payments fees (not netted off sales)  
3. **Paper copy-aid PDF** — ONTVANGSTEN grid matching the physical book (for manual copy)

Not affiliated with Starterslabo or Shopify. You need your own portal login and Shopify Admin token. Credentials are never stored in this repo.

## Install

Clone this repo **as the skill folder** (`SKILL.md` at the root):

```bash
# Cursor — this project
git clone https://github.com/c1sc0c0/starterslabo-shopify.git .cursor/skills/starterslabo-shopify

# Cursor — all projects
git clone https://github.com/c1sc0c0/starterslabo-shopify.git ~/.cursor/skills/starterslabo-shopify

# Claude Code — this project
git clone https://github.com/c1sc0c0/starterslabo-shopify.git .claude/skills/starterslabo-shopify
```

Start a new agent chat so the skill is picked up.

Portal draft scripts (`create_draft_invoice.py` / `create_draft_expense.py`) are expected in a sibling `skills/` workspace (see [starterlabo-invoices](https://github.com/c1sc0c0/starterlabo-invoices) and [starterslabo-expenses](https://github.com/c1sc0c0/starterslabo-expenses)). Plan-only + paper PDF work without them.

## Setup

```bash
cd /path/to/starterslabo-shopify
cp .env.example .env   # never commit .env
# Shopify: SHOPIFY_REBELCHALK_TOKEN or macOS Keychain (see SKILL.md)
# Portal + DO address + DOSSIER_NR + DO_BOOK_START in .env or environment
```

Paper PDF deps:

```bash
uv run --with reportlab --with pypdf python scripts/sync_shopify.py --month YYYY-MM
# or: pip install -r scripts/requirements.txt
```

## Use

Tell the agent something like:

> Sync Shopify B2C sales for September into Starterslabo dagontvangsten and give me the paper book PDF to copy.

Or run manually:

```bash
# Plan only — writes shopify-sync/YYYY-MM/ (gitignored locally)
uv run --with reportlab --with pypdf \
  python scripts/sync_shopify.py --month 2026-09

# Regenerate paper PDF from existing plan.json (no Shopify call)
uv run --with reportlab --with pypdf \
  python scripts/sync_shopify.py --month 2026-09 --paper-pdf-only

# Upsert portal CONCEPTS / close month (needs portal scripts + credentials)
python scripts/sync_shopify.py --month 2026-09 --apply
python scripts/sync_shopify.py --month 2026-09 --close
```

### Paper book header

| Field | Source |
|-------|--------|
| MAAND | Dutch month + year from `--month` |
| B.T.W. Nr. | `STARTERSLABO_BTW_NR` + `(STARTERSLABO_DOSSIER_NR)` |
| N° | Month index from `STARTERSLABO_DO_BOOK_START` (page 1 = first month) |

Copy the PDF into the numbered physical ONTVANGSTEN book. The PDF is a **copy-aid**, not a legal substitute for the paper register (Starterslabo FAQ).

## Privacy

- No real credentials, order dumps, or filled monthly PDFs in this repo.
- `.gitignore` excludes `.env`, `.venv/`, `shopify-sync/`, and generated paper PDFs.
- `assets/dagontvangstenboek-voorbeeld.pdf` is the FAQ sample ONTVANGSTEN page (layout reference only; not your books).
- Do not paste portal passwords or Shopify tokens into issues/PRs.

## Related

- [starterslabo-skills](https://github.com/c1sc0c0/starterslabo-skills) — index of all skills  
- [starterlabo-invoices](https://github.com/c1sc0c0/starterlabo-invoices) — verkoopfactuur drafts  
- [starterslabo-expenses](https://github.com/c1sc0c0/starterslabo-expenses) — aankoopfactuur SL  

## License

MIT for this skill’s code and instructions. Starterslabo’s website, portal, and documents remain theirs. Shopify is a trademark of Shopify Inc.
