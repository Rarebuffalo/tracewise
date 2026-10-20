"""Email bodies: the verification email (to the person) and the owner notification (to WAITLIST_OWNER_NOTIFY_EMAIL).

Plain-text and HTML versions; every interpolated value is escaped. The verification link is the only place the raw
token ever appears, and it is built in memory just before sending.
"""

from __future__ import annotations

from html import escape

INK = "#0B1220"
PAPER = "#F3EFE6"
CARD = "#FCFBF8"
SLATE = "#5B6474"
CYAN_INK = "#0B6A80"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def _frame(inner: str, footer: str) -> str:
    return f"""<!doctype html><html><body
 style="margin:0;background:{PAPER};padding:32px 12px;font-family:{FONT};color:{INK}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="560" cellspacing="0" cellpadding="0"
 style="max-width:560px;width:100%;background:{CARD};border-top:3px solid {INK}">
<tr><td style="padding:28px 32px 8px;font-size:20px;font-weight:700;letter-spacing:-0.02em">Tracewise</td></tr>
<tr><td style="padding:0 32px 28px;font-size:16px;line-height:1.6">{inner}</td></tr>
</table>
<p style="max-width:560px;font-size:12px;line-height:1.5;color:{SLATE};margin:16px auto 0">{footer}</p>
</td></tr></table></body></html>"""


def verification(link: str, unsubscribe_link: str, postal_address: str | None, ttl_hours: int) -> tuple[str, str, str]:
    subject = "Confirm your spot on the Tracewise early-access list"
    addr_text = f"\n{postal_address}" if postal_address else ""
    text = (
        "Thanks for asking for early access to Tracewise.\n\n"
        f"Confirm your email to join the list (the link works once and expires in {ttl_hours} hours):\n{link}\n\n"
        "If you didn't ask for this, ignore this email; without confirmation you won't hear from us again "
        "and the request is deleted after 7 days.\n\n"
        "Tracewise is pre-release software. We'll email you when a pilot slot opens.\n"
        f"Remove me from the list: {unsubscribe_link}{addr_text}\n"
    )
    inner = (
        '<p style="margin:0 0 16px">Thanks for asking for early access to Tracewise.</p>'
        '<p style="margin:0 0 24px">Confirm your email to join the list.</p>'
        f'<p style="margin:0 0 24px"><a href="{escape(link)}" style="display:inline-block;background:{INK};color:{PAPER};'
        'text-decoration:none;font-weight:650;padding:14px 22px;border-radius:999px">Confirm my spot</a></p>'
        f'<p style="margin:0 0 16px;font-size:14px;color:{SLATE}">The link works once and expires in {ttl_hours} hours. '
        "If the button doesn't work, paste this into your browser:<br>"
        f'<span style="word-break:break-all;color:{CYAN_INK}">{escape(link)}</span></p>'
        f'<p style="margin:0;font-size:14px;color:{SLATE}">Didn\'t ask for this? Ignore this email: without confirmation '
        "you won't hear from us again, and the request is deleted after 7 days.</p>"
    )
    footer = (
        "Tracewise is pre-release software. "
        f'<a href="{escape(unsubscribe_link)}" style="color:{SLATE}">Remove me from the list</a>'
        + (f"<br>{escape(postal_address)}" if postal_address else "")
    )
    return subject, text, _frame(inner, footer)


def owner_notification(payload: dict[str, object]) -> tuple[str, str, str]:
    """`payload` is the snapshot stored in the outbox row (no tokens, no IPs)."""
    rows = [
        ("Email", str(payload.get("email", ""))),
        ("Confirmed at (UTC)", str(payload.get("confirmed_at", ""))),
        ("Signed up at (UTC)", str(payload.get("created_at", ""))),
        ("GitHub username", str(payload.get("github_login") or "—")),
        ("Product-updates consent", "yes" if payload.get("updates_consent") else "no"),
        ("CI fails", str(payload.get("ci_failure_freq") or "not answered yet")),
        ("Disposable-mail domain", "yes (flagged)" if payload.get("disposable_domain") else "no"),
    ]
    subject = f"New confirmed Tracewise signup: {payload.get('email', '')}"
    text = (
        "A new person confirmed their early-access signup.\n\n"
        + "\n".join(f"{k}: {v}" for k, v in rows)
        + ("\n\nThis notification is sent once per confirmed signup. Exports and deletion: python -m tracewise.waitlist.admin\n")
    )
    table = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:{SLATE};font-size:14px;white-space:nowrap">{escape(k)}</td>'
        f'<td style="padding:6px 0;font-size:14px">{escape(v)}</td></tr>'
        for k, v in rows
    )
    inner = (
        '<p style="margin:0 0 16px">A new person confirmed their early-access signup.</p>'
        f'<table role="presentation" cellspacing="0" cellpadding="0">{table}</table>'
    )
    footer = "Sent once per confirmed signup by the Tracewise waitlist service."
    return subject, text, _frame(inner, footer)
