#!/usr/bin/env python3
"""Plan (and optionally draft) Starterslabo dagontvangsten + Shopify fees.

Shopify Admin token: env SHOPIFY_REBELCHALK_TOKEN, or macOS Keychain
service scout_shopify_rebelchalk (same as Phoenix rebelchalk scripts).

Default is plan-only: write a month folder with a JSON plan, a paper-style
dagontvangstenboek text file, and a fee receipt. Portal writes are opt-in.
Re-running --apply upserts the same month's CONCEPTS (SHOPIFY-DO-YYYYMM /
SHOPIFY-FEE-YYYYMM). --close upserts then Verstuur. Booked invoices are
never overwritten.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

SHOP = os.environ.get("SHOPIFY_SHOP", "rebelchalk.myshopify.com")
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10")
KEYCHAIN_SERVICE = os.environ.get(
    "SHOPIFY_KEYCHAIN_SERVICE", "scout_shopify_rebelchalk"
)
FEE_ACCOUNT = os.environ.get("STARTERSLABO_SHOPIFY_FEE_ACCOUNT", "612125")


def workspace_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "skills" / "create_draft_invoice.py").exists():
            return parent
        if (parent / ".cursor" / "skills" / "starterlabo-invoices").exists():
            return parent
    return Path.cwd()


def load_skills_env() -> None:
    """Pick up STARTERSLABO_* from skills/.env without printing values."""
    path = workspace_root() / "skills" / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def keychain(account: str) -> str:
    try:
        out = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                account,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def shopify_token() -> str:
    env = (os.environ.get("SHOPIFY_REBELCHALK_TOKEN") or "").strip()
    if env.startswith("shpat_") or env.startswith("shpca_"):
        return env
    admin = keychain("api")
    if admin.startswith("shpat_") or admin.startswith("shpca_"):
        return admin
    client_id = keychain("client_id")
    client_secret = keychain("client_secret") or (
        admin if admin.startswith("shpss_") else ""
    )
    if client_id and client_secret:
        data = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }
        ).encode()
        req = urllib.request.Request(
            f"https://{SHOP}/admin/oauth/access_token",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode() or "{}")
        token = (payload.get("access_token") or "").strip()
        if not token:
            raise SystemExit("Shopify client_credentials returned no access_token")
        return token
    raise SystemExit(
        "No Shopify token. Set SHOPIFY_REBELCHALK_TOKEN or Keychain "
        f"service {KEYCHAIN_SERVICE} account api."
    )


def api(token: str, path: str) -> dict:
    url = f"https://{SHOP}/admin/api/{API_VERSION}{path}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "X-Shopify-Access-Token": token,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Shopify HTTP {exc.code} {path}: {body[:400]}") from exc


def money(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def parse_month(value: str) -> tuple[date, date]:
    year, month = value.split("-", 1)
    y, m = int(year), int(month)
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def in_month(created_at: str, start: date, end: date) -> bool:
    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    return start <= dt <= end


def is_b2b(order: dict) -> bool:
    for blob in (
        order.get("shipping_address") or {},
        order.get("billing_address") or {},
        (order.get("customer") or {}).get("default_address") or {},
    ):
        if (blob.get("company") or "").strip():
            return True
    return False


def fmt_eur(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}".replace(".", ",")


def require_do_identity() -> dict[str, str]:
    fields = {
        "name": os.environ.get("STARTERSLABO_DO_NAME", "DO Your Name").strip(),
        "email": (os.environ.get("STARTERSLABO_DO_EMAIL") or "").strip(),
        "address": (os.environ.get("STARTERSLABO_DO_ADDRESS") or "").strip(),
        "city": (os.environ.get("STARTERSLABO_DO_CITY") or "").strip(),
        "postal": (os.environ.get("STARTERSLABO_DO_POSTAL") or "").strip(),
    }
    missing = [k for k in ("address", "city", "postal") if not fields[k]]
    if missing:
        raise SystemExit(
            "Dagontvangsten need YOUR address on the invoice. Set "
            "STARTERSLABO_DO_ADDRESS, STARTERSLABO_DO_CITY, STARTERSLABO_DO_POSTAL "
            f"(missing: {', '.join(missing)})."
        )
    return fields


def collect(token: str, start: date, end: date) -> dict:
    orders = api(token, "/orders.json?status=any&limit=250").get("orders") or []
    fees = api(
        token, "/shopify_payments/balance/transactions.json?limit=250"
    ).get("transactions") or []
    paid_b2c = []
    skipped = []
    for order in orders:
        created = order.get("created_at") or ""
        if not in_month(created, start, end):
            continue
        status = (order.get("financial_status") or "").lower()
        rec = {
            "id": order.get("id"),
            "name": order.get("name"),
            "created_at": created,
            "financial_status": status,
            "total": str(money(order.get("total_price"))),
            "tax": str(money(order.get("total_tax"))),
            "taxes_included": bool(order.get("taxes_included")),
            "currency": order.get("currency"),
            "country": (order.get("shipping_address") or {}).get("country_code")
            or (order.get("billing_address") or {}).get("country_code"),
            "lines": [
                {
                    "title": li.get("title"),
                    "sku": li.get("sku"),
                    "qty": li.get("quantity"),
                    "price": li.get("price"),
                }
                for li in order.get("line_items") or []
            ],
            "tax_lines": [
                {"title": t.get("title"), "rate": t.get("rate"), "price": t.get("price")}
                for t in order.get("tax_lines") or []
            ],
        }
        if status != "paid":
            rec["reason"] = f"financial_status={status}"
            skipped.append(rec)
            continue
        if is_b2b(order):
            rec["reason"] = "looks B2B (company set) — named factuur, not dagontvangsten"
            skipped.append(rec)
            continue
        paid_b2c.append(rec)

    fee_rows = []
    order_ids = {row["id"] for row in paid_b2c}
    for row in fees:
        processed = (row.get("processed_at") or "")[:10]
        try:
            processed_d = date.fromisoformat(processed) if processed else None
        except ValueError:
            processed_d = None
        oid = row.get("source_order_id")
        if oid in order_ids or (
            processed_d and start <= processed_d <= end and row.get("type") == "charge"
        ):
            fee_rows.append(
                {
                    "id": row.get("id"),
                    "type": row.get("type"),
                    "amount": row.get("amount"),
                    "fee": row.get("fee"),
                    "net": row.get("net"),
                    "source_order_id": oid,
                    "processed_at": row.get("processed_at"),
                }
            )

    totals_by_rate: dict[str, Decimal] = defaultdict(Decimal)
    for order in paid_b2c:
        totals_by_rate[order_vat_rate(order)] += money(order["total"])

    fee_total = sum((money(r["fee"]) for r in fee_rows), Decimal("0"))
    sales_total = sum((money(r["total"]) for r in paid_b2c), Decimal("0"))
    return {
        "shop": SHOP,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sales_total_incl": str(sales_total),
        "fee_total": str(fee_total),
        "totals_by_vat": {k: str(v) for k, v in totals_by_rate.items()},
        "orders": paid_b2c,
        "fees": fee_rows,
        "skipped": skipped,
    }


def order_vat_rate(order: dict) -> str:
    """Return VAT rate key '0'|'6'|'12'|'21' for an order (incl. amount column)."""
    if order.get("tax_lines"):
        return str(int(Decimal(str(order["tax_lines"][0]["rate"])) * 100))
    return "21"


# Paper DO omschrijving: what the shop sells (not Shopify promo titles like COMBO DEAL).
DO_OMSCHRIJVING = "online sales chalk & skincare for climbers"


def product_omschrijving(line: dict | None = None) -> str:
    """Omschrijving for the paper DO book / bijlage."""
    return DO_OMSCHRIJVING


def order_description(order: dict) -> str:
    """Day/order label for the paper DO grid."""
    return DO_OMSCHRIJVING


def order_audit_description(order: dict) -> str:
    """Bijlage line: shop omschrijving + Shopify line titles for audit."""
    titles = ", ".join(
        f"{li.get('qty') or 1}× {li.get('title') or li.get('sku') or 'webshop'}"
        for li in order.get("lines") or []
    ) or "webshop"
    return f"{DO_OMSCHRIJVING} ({titles})"


def paper_rows(plan: dict) -> list[dict]:
    """One row per calendar day for the paper ONTVANGSTEN grid.

    Amounts in v0/v6/v12/v21 are tax-included (same as the printed form).
    Quiet days get total_incl=0 and empty description.
    Omschrijving: shop category (not promo titles like COMBO DEAL).
    """
    start = date.fromisoformat(plan["period"]["start"])
    end = date.fromisoformat(plan["period"]["end"])
    last = end.day
    by_day: dict[int, dict] = {}
    for day_n in range(1, last + 1):
        by_day[day_n] = {
            "day": day_n,
            "description": "",
            "total_incl": Decimal("0"),
            "tax": Decimal("0"),
            "v0": Decimal("0"),
            "v6": Decimal("0"),
            "v12": Decimal("0"),
            "v21": Decimal("0"),
            "_parts": [],
        }
    for order in plan.get("orders") or []:
        created = (order.get("created_at") or "")[:10]
        if not created:
            continue
        d = date.fromisoformat(created)
        if d.month != start.month or d.year != start.year:
            continue
        row = by_day[d.day]
        total = money(order["total"])
        tax = money(order.get("tax"))
        rate = order_vat_rate(order)
        row["total_incl"] += total
        row["tax"] += tax
        key = {"0": "v0", "6": "v6", "12": "v12", "21": "v21"}.get(rate, "v21")
        row[key] += total
        for part in order_description(order).split(", "):
            if part and part not in row["_parts"]:
                row["_parts"].append(part)
    out: list[dict] = []
    for day_n in range(1, last + 1):
        row = by_day[day_n]
        parts = row.pop("_parts")
        row["description"] = ", ".join(parts)
        out.append(row)
    return out


def paper_month_totals(plan: dict) -> dict[str, Decimal]:
    """Footer totals for the paper book (must match txt / portal DO).

    Incl. amounts go in TOTALEN + VAT columns. Excl. and BTW are also filled
    under each active VAT column (Ruth: 21% kolom = excl + BTW van de maand).
    """
    zero = Decimal("0")
    totals: dict[str, Decimal] = {
        "incl": zero,
        "excl": zero,
        "tax": zero,
        "v0": zero,
        "v6": zero,
        "v12": zero,
        "v21": zero,
        "v0_excl": zero,
        "v6_excl": zero,
        "v12_excl": zero,
        "v21_excl": zero,
        "v0_tax": zero,
        "v6_tax": zero,
        "v12_tax": zero,
        "v21_tax": zero,
    }
    for order in plan.get("orders") or []:
        total = money(order["total"])
        tax = money(order.get("tax"))
        rate = order_vat_rate(order)
        col = {"0": "v0", "6": "v6", "12": "v12", "21": "v21"}.get(rate, "v21")
        totals["incl"] += total
        totals["tax"] += tax
        totals["excl"] += total - tax
        totals[col] += total
        totals[f"{col}_excl"] += total - tax
        totals[f"{col}_tax"] += tax
    # Prefer plan sales_total_incl when present (single source of truth)
    if plan.get("sales_total_incl") is not None:
        totals["incl"] = money(plan["sales_total_incl"])
        totals["excl"] = totals["incl"] - totals["tax"]
    return totals


def write_book(plan: dict, dest: Path) -> None:
    """Per-order audit text (portal bijlage). Daily aggregation is for the paper PDF."""
    lines = [
        f"Dagontvangstenboek  {plan['period']['start']} → {plan['period']['end']}",
        f"Shop: {plan['shop']}",
        "",
        "Datum        Order    Land  Incl. EUR  BTW     Omschrijving",
        "-" * 72,
    ]
    for order in plan["orders"]:
        day = (order["created_at"] or "")[:10]
        vat = order["tax"]
        title = order_audit_description(order)
        lines.append(
            f"{day}  {order['name']:<8} {order.get('country') or '?':<4}  "
            f"{order['total']:>8}  {vat:>6}  {title}"
        )
    lines += [
        "-" * 72,
        f"Totaal incl. btw: {plan['sales_total_incl']} EUR",
        "",
        "Shopify Payments fees (niet in mindering op omzet; aparte onkostennota):",
    ]
    for fee in plan["fees"]:
        lines.append(
            f"  {fee.get('processed_at')}  order {fee.get('source_order_id')}  "
            f"fee {fee.get('fee')}  net {fee.get('net')}"
        )
    lines.append(f"Totaal fees: {plan['fee_total']} EUR")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_fee_receipt(plan: dict, dest: Path) -> None:
    lines = [
        "Shopify Payments — transactiekosten (API extract)",
        f"Shop: {plan['shop']}",
        f"Periode: {plan['period']['start']} → {plan['period']['end']}",
        "",
    ]
    for fee in plan["fees"]:
        lines.append(
            f"- id {fee['id']}  type {fee['type']}  amount {fee['amount']}  "
            f"fee {fee['fee']}  net {fee['net']}  order {fee.get('source_order_id')}"
        )
    lines.append(f"\nTotaal fee: {plan['fee_total']} EUR")
    lines.append(
        "\nDit is een extract van Shopify Payments balance transactions; "
        "voeg de Shopify billing/payout PDF toe als die later binnenkomt."
    )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def invoice_cmd(plan: dict, identity: dict, book: Path) -> list[str]:
    totals = plan["totals_by_vat"]
    if len(totals) != 1:
        raise SystemExit(
            f"Need exactly one VAT rate for a single DO line, got {totals}"
        )
    vat, total = next(iter(totals.items()))
    end = plan["period"]["end"]
    return [
        "create_draft_invoice.py",
        "--name",
        identity["name"],
        "--email",
        identity["email"],
        "--address",
        identity["address"],
        "--city",
        identity["city"],
        "--postal",
        identity["postal"],
        "--country",
        "BE",
        "--description",
        f"Dagontvangsten Shopify {end[:7]} (webshop B2C)",
        "--reference",
        f"SHOPIFY-DO-{end[:7].replace('-', '')}",
        "--upsert",
        "--quantity",
        "1",
        "--price",
        fmt_eur(money(total)),
        "--vat",
        vat,
        "--tax-included",
        "--invoice-date",
        end,
        "--paid",
        "--no-peppol",
        "--notes",
        f"Zie bijlage dagontvangstenboek. Omzet {plan['sales_total_incl']} EUR incl. "
        f"Shopify-fee {plan['fee_total']} EUR apart als onkosten.",
        "--attachment",
        str(book),
    ]


def expense_cmd(plan: dict, receipt: Path) -> list[str]:
    end = plan["period"]["end"]
    return [
        "create_draft_expense.py",
        "--title",
        f"Onk. Shopify fee {end[:7]}",
        "--account",
        FEE_ACCOUNT,
        "--amount",
        fmt_eur(money(plan["fee_total"])),
        "--date",
        end,
        "--invoice-nr",
        f"SHOPIFY-FEE-{end[:7].replace('-', '')}",
        "--upsert",
        "--description",
        "Shopify Payments transactiekosten op B2C webshop-verkopen. "
        "Aparte kost; niet in mindering op dagontvangsten-omzet.",
        "--attachment",
        str(receipt),
    ]


def run_portal(script: str, args: list[str], skills_dir: Path, extra: list[str]) -> int:
    cmd = ["uv", "run", "python", script, *args[1:], *extra]
    print("+", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(skills_dir))


def book_page_number(month: str) -> int:
    """1-based page index: one page per month from STARTERSLABO_DO_BOOK_START."""
    start_s = (os.environ.get("STARTERSLABO_DO_BOOK_START") or "").strip()
    if not start_s:
        print(
            "STARTERSLABO_DO_BOOK_START unset — paper PDF N° = 1 "
            "(set YYYY-MM of your first book page for sequential numbering)",
            file=sys.stderr,
        )
        return 1
    try:
        sy, sm = (int(x) for x in start_s.split("-", 1))
        y, m = (int(x) for x in month.split("-", 1))
    except ValueError as exc:
        raise SystemExit(
            f"Bad month/STARTERSLABO_DO_BOOK_START (want YYYY-MM): {month!r} / {start_s!r}"
        ) from exc
    idx = (y - sy) * 12 + (m - sm) + 1
    if idx < 1:
        raise SystemExit(
            f"Month {month} is before book start {start_s} "
            "(set STARTERSLABO_DO_BOOK_START)"
        )
    return idx


def write_paper_pdf_for_plan(plan: dict, dest: Path) -> Path | None:
    """Write ONTVANGSTEN copy-aid PDF next to the txt book. Returns path or None."""
    try:
        from dagontvangsten_paper_pdf import ensure_blank_template, write_paper_pdf
    except ImportError:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            from dagontvangsten_paper_pdf import ensure_blank_template, write_paper_pdf
        except ImportError as exc:
            print(
                f"Paper PDF skipped (install reportlab + pypdf): {exc}",
                file=sys.stderr,
            )
            return None
    ensure_blank_template()
    # Kandidaat-ondernemers use Starterslabo's BTW; dossiernr is personal.
    btw_nr = (
        os.environ.get("STARTERSLABO_BTW_NR") or "BE 0876 478 439"
    ).strip()
    dossier = (
        os.environ.get("STARTERSLABO_DOSSIER_NR")
        or os.environ.get("STARTERSLABO_KO_NR")
        or ""
    ).strip()
    if dossier:
        btw_nr = f"{btw_nr} ({dossier})"
    month = plan["period"]["start"][:7]
    page_no = book_page_number(month)
    rows = paper_rows(plan)
    totals = paper_month_totals(plan)
    return write_paper_pdf(
        plan,
        dest,
        rows=rows,
        totals=totals,
        btw_nr=btw_nr,
        page_no=page_no,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        default=date.today().strftime("%Y-%m"),
        help="YYYY-MM to sync (default: current month)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upsert portal CONCEPTS for this month (create or rewrite the same drafts)",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Upsert then Verstuur (lock the month). Use at month end only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --apply/--close: fill forms but do not save/send",
    )
    parser.add_argument(
        "--apply-dry-run",
        action="store_true",
        help=argparse.SUPPRESS,  # alias
    )
    parser.add_argument(
        "--paper-pdf-only",
        action="store_true",
        help="Regenerate dagontvangstenboek-paper.pdf from existing plan.json (no Shopify call)",
    )
    args = parser.parse_args()
    load_skills_env()
    if args.apply_dry_run:
        args.apply = True
        args.dry_run = True
    if args.close and args.apply:
        raise SystemExit("Use --apply during the month, or --close at month end, not both")
    if args.close:
        args.apply = True
    if args.paper_pdf_only and (args.apply or args.close):
        raise SystemExit("--paper-pdf-only cannot be combined with --apply/--close")

    start, end = parse_month(args.month)
    root = workspace_root()
    out = root / "shopify-sync" / args.month
    out.mkdir(parents=True, exist_ok=True)

    if args.paper_pdf_only:
        plan_path = out / "plan.json"
        if not plan_path.is_file():
            raise SystemExit(f"No plan.json at {plan_path}; run without --paper-pdf-only first")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        paper = write_paper_pdf_for_plan(plan, out / "dagontvangstenboek-paper.pdf")
        if not paper:
            return 1
        print(f"Wrote paper PDF: {paper}")
        return 0

    token = shopify_token()
    plan = collect(token, start, end)
    (out / "plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    book = out / "dagontvangstenboek.txt"
    fees = out / "shopify-fees.txt"
    write_book(plan, book)
    write_fee_receipt(plan, fees)
    paper = write_paper_pdf_for_plan(plan, out / "dagontvangstenboek-paper.pdf")

    yyyymm = args.month.replace("-", "")
    sale_ref = f"SHOPIFY-DO-{yyyymm}"
    fee_nr = f"SHOPIFY-FEE-{yyyymm}"
    (out / "portal.json").write_text(
        json.dumps(
            {
                "sale_reference": sale_ref,
                "fee_invoice_nr": fee_nr,
                "period": plan["period"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Period     : {start} → {end}")
    print(f"Sale ref   : {sale_ref}  (one verkoop concept, upserted)")
    print(f"Fee nr     : {fee_nr}  (one onkosten concept, upserted)")
    print(f"B2C paid   : {len(plan['orders'])} orders, {plan['sales_total_incl']} EUR incl.")
    print(f"Fees       : {plan['fee_total']} EUR ({len(plan['fees'])} tx)")
    print(f"Skipped    : {len(plan['skipped'])}")
    for skip in plan["skipped"]:
        print(f"  - {skip.get('name')} {skip.get('reason')}")
    print(f"Wrote      : {out}")
    if paper:
        print(f"Paper PDF  : {paper}")

    if not plan["orders"]:
        print("Nothing to invoice.")
        return 0

    if not args.apply and not args.close:
        print("\nPlan only. Set STARTERSLABO_DO_ADDRESS/CITY/POSTAL then:")
        print("  --apply          upsert the month's CONCEPT (safe to re-run)")
        print("  --apply --dry-run  fill portal, don't save")
        print("  --close          upsert + Verstuur (end of month)")
        print("  --paper-pdf-only regenerate paper PDF from plan.json")
        return 0

    identity = require_do_identity()
    inv = invoice_cmd(plan, identity, book)
    exp = expense_cmd(plan, fees) if money(plan["fee_total"]) > 0 else None
    print("\nProposed verkoop (dagontvangsten):")
    print(" ", " ".join(inv))
    if exp:
        print("\nProposed onkosten (Shopify fee):")
        print(" ", " ".join(exp))

    skills_dir = root / "skills"
    extra: list[str] = []
    if args.dry_run:
        extra.append("--dry-run")
    elif args.close:
        extra.append("--send")
    mode = "close (Verstuur)" if args.close and not args.dry_run else (
        "dry-run" if args.dry_run else "upsert concept"
    )
    print(f"\nPortal mode: {mode}")
    rc = run_portal(inv[0], inv, skills_dir, extra)
    if rc != 0:
        return rc
    if exp:
        rc = run_portal(exp[0], exp, skills_dir, extra)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
