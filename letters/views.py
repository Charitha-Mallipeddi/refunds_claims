from __future__ import annotations
import os, json
from io import BytesIO
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import select_template
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.utils.text import slugify
from django.contrib.staticfiles import finders
from django.views.decorators.http import require_GET

# ------------------------------
# Constants / friendly names
# ------------------------------

REASONS = {
    "LIRR": {
        "INV_TKT": "Invalid ticket",
        "DUP_REQ": "Duplicate request",
        "EXP_WIN": "Refund period expired",
        "INS_DOC": "Insufficient documentation",
    },
    "MNR": {
        "INV_TKT": "Invalid ticket",
        "DUP_REQ": "Duplicate request",
        "EXP_WIN": "Refund period expired",
        "INS_DOC": "Insufficient documentation",
    },
}

# ------------------------------
# Basic pages
# ------------------------------

def index(request):
    return render(request, "letters/index.html")

# ------------------------------
# Template selection
# ------------------------------

def _templates_for(railroad: str, force: str | None = None) -> dict:
    """
    Choose templates. Prefer the centered email template by default.
    force can be: 'email' or 'v2'
    """
    rr = (railroad or "LIRR").upper()
    label = "Long Island Rail Road" if rr == "LIRR" else "Metro-North Railroad"

    if force == "v2":
        html_candidates = ["letters/denial_letter_v2.html"]
    elif force == "email":
        html_candidates = ["letters/denial_email.html"]
    else:
        # DEFAULT: try the centered one first, then fallback
        html_candidates = ["letters/denial_email.html", "letters/denial_letter_v2.html"]

    text_candidates = [f"letters/denial_body_{rr.lower()}.txt", "letters/denial_body.txt"]
    return {"rr": rr, "label": label, "html_candidates": html_candidates, "text_candidates": text_candidates}

# ------------------------------
# Helpers
# ------------------------------

def _railroad_meta(rr: str) -> dict:
    rr = (rr or "LIRR").upper()
    if rr == "LIRR":
        return {
            "label": "Long Island Rail Road",
            "dept_name": "LIRR Refund Department",
            "footer_line": "MTA Long Island Rail Road is an agency of the Metropolitan Transportation Authority, State of New York, Janno Lieber, Chairman & CEO",
        }
    return {
        "label": "Metro-North Railroad",
        "dept_name": "Metro-North Railroad Refund Department",
        "footer_line": "MTA Metro-North Railroad is an agency of the Metropolitan Transportation Authority, State of New York, Janno Lieber, Chairman & CEO",
    }

def _reason_text(railroad: str, code_or_text: str) -> str:
    rr = (railroad or "LIRR").upper()
    if code_or_text in (REASONS.get(rr) or {}):
        return REASONS[rr][code_or_text]
    return code_or_text

def _ctx_from_post(request):
    return {
        "railroad": (request.POST.get("railroad") or "LIRR").strip(),
        "customer_name": (request.POST.get("customer_name") or "").strip(),
        "customer_email": (request.POST.get("customer_email") or "").strip(),
        "denial_reason": request.POST.get("denial_reason") or "",
        "notes": request.POST.get("notes") or "",
        "claim_id": (request.POST.get("claim_id") or "").strip(),
        "address1": (request.POST.get("address1") or "").strip(),
        "address2": (request.POST.get("address2") or "").strip(),
        "city": (request.POST.get("city") or "").strip(),
        "state": (request.POST.get("state") or "").strip(),
        "zip": (request.POST.get("zip") or "").strip(),
    }

def _ctx_from_json(payload: dict):
    return {
        "railroad": (payload.get("railroad") or "LIRR").strip(),
        "customer_name": (payload.get("customerName") or "").strip(),
        "customer_email": (payload.get("customerEmail") or "").strip(),
        "denial_reason": _reason_text(payload.get("railroad") or "LIRR", payload.get("denialReasonCode") or ""),
        "notes": payload.get("notes") or "",
        "claim_id": (payload.get("claimId") or "").strip(),
        "address1": (payload.get("address1") or "").strip(),
        "address2": (payload.get("address2") or "").strip(),
        "city": (payload.get("city") or "").strip(),
        "state": (payload.get("state") or "").strip(),
        "zip": (payload.get("zip") or "").strip(),
    }

def _lookup_claim(claim_id: str):
    if not claim_id:
        return None
    try:
        from .models import Claim  # optional
    except Exception:
        return None
    try:
        return Claim.objects.get(claim_id=claim_id)
    except Claim.DoesNotExist:
        return None

def _maybe_merge_claim(ctx: dict) -> dict:
    c = _lookup_claim(ctx.get("claim_id"))
    if not c:
        return ctx
    ctx.setdefault("railroad", c.railroad)
    ctx.setdefault("customer_name", c.customer_name)
    ctx.setdefault("customer_email", c.customer_email)
    ctx.setdefault("address1", c.address1)
    ctx.setdefault("address2", c.address2)
    ctx.setdefault("city", c.city)
    ctx.setdefault("state", c.state)
    ctx.setdefault("zip", c.zip)
    return ctx

def _enrich_letter_ctx(ctx: dict) -> dict:
    meta = _railroad_meta(ctx.get("railroad"))
    ctx["rr"] = (ctx.get("railroad") or "LIRR").upper()
    ctx["rr_label"] = meta["label"]
    ctx["issue_date"] = datetime.now().strftime("%-m/%-d/%Y")
    ctx["dept_name"] = meta["dept_name"]
    ctx["footer_line"] = meta["footer_line"]
    ctx.setdefault("contact_url", "https://contact.mta.info/s/customer-feedback")
    ctx.setdefault("contact_phone", "(718) 217-5477")
    ctx.setdefault("address_name", ctx.get("customer_name"))
    return ctx

def _render_email_html(ctx: dict, tinfo: dict) -> str:
    tmpl = select_template(tinfo["html_candidates"])
    # log which template is actually used (helps debugging)
    print("TEMPLATE_USED =>", getattr(tmpl, "origin", None) and tmpl.origin.name)
    return tmpl.render(ctx)

def _render_email_text(ctx: dict, tinfo: dict) -> str:
    tmpl = select_template(tinfo["text_candidates"])
    return tmpl.render(ctx)

def _html_to_pdf_bytes(html: str) -> bytes:
    """
    xhtml2pdf can stretch tables on 100% rules; we relax those a bit.
    """
    from xhtml2pdf import pisa
    html = html.replace("width:100%", "width:auto").replace("width: 100%", "width:auto")
    buf = BytesIO()

    def link_callback(uri, rel):
        if uri.startswith(settings.STATIC_URL):
            return finders.find(uri.replace(settings.STATIC_URL, ""))
        return uri

    result = pisa.CreatePDF(html, dest=buf, link_callback=link_callback)
    if result.err:
        raise RuntimeError("PDF generation failed.")
    return buf.getvalue()

def _save_pdf(pdf_bytes: bytes, railroad: str, claim_id: str) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y/%m")
    name = slugify(claim_id or datetime.now().strftime("tmp-%Y%m%d%H%M%S"))
    rel = f"letters/{(railroad or 'LIRR').upper()}/{stamp}/{name}.pdf"
    abs_path = os.path.join(settings.MEDIA_ROOT, rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(pdf_bytes)
    url = settings.MEDIA_URL + rel
    return abs_path, url

def _send_email(subject: str, to_email: str, text_body: str, html_body: str, attach_path: str | None = None):
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@local.refunds"),
        to=[to_email],
    )
    email.attach_alternative(html_body, "text/html")
    if attach_path and os.path.exists(attach_path):
        with open(attach_path, "rb") as f:
            email.attach(os.path.basename(attach_path), f.read(), "application/pdf")
    email.send()

# ------------------------------
# Views / endpoints
# ------------------------------

def preview_email(request):
    if request.method != "POST":
        return redirect("letters:index")
    ctx = _ctx_from_post(request)
    ctx["denial_reason"] = _reason_text(ctx["railroad"], ctx["denial_reason"])
    ctx = _maybe_merge_claim(ctx)
    ctx = _enrich_letter_ctx(ctx)
    force = request.GET.get("tpl") or request.POST.get("tpl")  # 'email' or 'v2'
    tinfo = _templates_for(ctx["railroad"], force=force)
    html = _render_email_html(ctx, tinfo)
    return HttpResponse(html)

def download_letter_pdf(request):
    if request.method != "POST":
        return redirect("letters:index")
    ctx = _ctx_from_post(request)
    ctx["denial_reason"] = _reason_text(ctx["railroad"], ctx["denial_reason"])
    ctx = _maybe_merge_claim(ctx)
    ctx = _enrich_letter_ctx(ctx)
    force = request.GET.get("tpl") or request.POST.get("tpl")
    tinfo = _templates_for(ctx["railroad"], force=force)
    html = _render_email_html(ctx, tinfo)
    pdf = _html_to_pdf_bytes(html)
    filename = f"refund_denial_{slugify(ctx['customer_name'] or 'customer')}_{ctx['railroad'].lower()}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

def send_email(request):
    if request.method != "POST":
        return redirect("letters:index")
    ctx = _ctx_from_post(request)
    if not ctx["customer_name"] or not ctx["customer_email"]:
        messages.error(request, "Enter customer name and email.")
        return redirect("letters:index")
    ctx["denial_reason"] = _reason_text(ctx["railroad"], ctx["denial_reason"])
    ctx = _maybe_merge_claim(ctx)
    ctx = _enrich_letter_ctx(ctx)
    force = request.GET.get("tpl") or request.POST.get("tpl")
    tinfo = _templates_for(ctx["railroad"], force=force)
    html_body = _render_email_html(ctx, tinfo)
    text_body = _render_email_text(ctx, tinfo)
    pdf_bytes = _html_to_pdf_bytes(html_body)
    pdf_path, _ = _save_pdf(pdf_bytes, ctx["railroad"], ctx.get("claim_id") or ctx["customer_name"])
    subject = f"Refund Decision — {tinfo['label']}" + (f" (Ref {ctx['claim_id']})" if ctx.get("claim_id") else "")
    _send_email(subject, ctx["customer_email"], text_body, html_body, pdf_path)
    messages.success(request, f"Email sent to {ctx['customer_email']}")
    return redirect("letters:index")

def api_generate_letter(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    ctx = _ctx_from_json(payload)
    ctx = _maybe_merge_claim(ctx)
    ctx = _enrich_letter_ctx(ctx)
    force = request.GET.get("tpl") or payload.get("tpl")
    tinfo = _templates_for(ctx["railroad"], force=force)

    html = _render_email_html(ctx, tinfo)
    pdf_bytes = _html_to_pdf_bytes(html)
    path, url = _save_pdf(pdf_bytes, ctx["railroad"], ctx["claim_id"] or ctx["customer_name"])

    emailed = False
    msg_id = None
    if ctx.get("customer_email"):
        text_body = _render_email_text(ctx, tinfo)
        subject = f"Refund Decision — {tinfo['label']}" + (f" (Ref {ctx['claim_id']})" if ctx.get("claim_id") else "")
        _send_email(subject, ctx["customer_email"], text_body, html, path)
        emailed = True
        msg_id = "local-email"

    return JsonResponse({"status": "ok", "emailed": emailed, "messageId": msg_id, "pdf": {"path": path, "url": url}})

@require_GET
def api_claim(request, claim_id: str):
    c = _lookup_claim(claim_id)
    if not c:
        return JsonResponse({"found": False}, status=404)
    return JsonResponse({
        "found": True,
        "railroad": c.railroad,
        "customer_name": c.customer_name,
        "customer_email": c.customer_email,
        "address1": c.address1,
        "address2": c.address2,
        "city": c.city,
        "state": c.state,
        "zip": c.zip,
    })
