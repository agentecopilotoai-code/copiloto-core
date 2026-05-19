"""Quote helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any


def _compute_quote_subtotal(line_items: list) -> float:
    return sum(item['qty'] * item['unit_price'] for item in line_items)


def _build_quote_summary_text(sr: Any, quote: Any) -> str:
    items = quote['line_items'] if isinstance(quote['line_items'], list) else json.loads(quote['line_items'])
    lines = [f"- {it['description']}: {it['qty']} x {it['unit_price']:,.0f} = {it['qty'] * it['unit_price']:,.0f}" for it in items]
    items_block = '\n'.join(lines) if lines else '(sin ítems)'
    valid_str = ''
    if quote['valid_until']:
        valid_str = f"\nVálida hasta: {quote['valid_until'].strftime('%Y-%m-%d %H:%M')}"
    return (
        f"*Cotización orientativa*\n"
        f"Servicio: {sr['service_type']}\n\n"
        f"{items_block}\n\n"
        f"Subtotal: {quote['subtotal']:,.0f} {quote['currency']}\n"
        f"Descuento: {quote['discount_total']:,.0f}\n"
        f"Impuestos: {quote['tax_total']:,.0f}\n"
        f"*Total: {quote['grand_total']:,.0f} {quote['currency']}*"
        f"{valid_str}"
    )
