from .forms import LetterForm
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.template.loader import render_to_string
from django.conf import settings

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

import io
import uuid
import os
import json
import re


SAMPLE = {
    "order_id": "11111",
    "reason_code": "NO_REMAINING_VALUE",
    "customer": {
        "name": "Thomas Knierim",
        "email": "example@gmail.com",
        "address_line1": "2086 5th Avenue, Apt# 3A",
        "address_line2": "",
        "city": "New York",
        "state": "NY",
        "zip": "10035",
    },
    "body_vars": {
        "website_url": "https://www.new.mta.info",
        "contact_url": "https://contact.mta.info/s/customer-feedback",
        "support_phone": "(718) 217-5477",
    },
}


def index(request):
    """Simple home with two buttons."""
    return render(request, "letters/index.html", {"sample": SAMPLE})


@csrf_exempt
def render_email(request):
    """
    Renders the denial email HTML.
    POST JSON with the same structure as SAMPLE to override.
    """
    data = SAMPLE
    if request.method == "POST" and request.body:
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            pass
    html = render_to_string("letters/denial_email.html", data)
    return HttpResponse(html)



def _load_request_data(request):
    data = SAMPLE
    if request.method == "POST" and request.body:
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            pass
    return data


def _draw_logo_and_header(c, width, height, order_id):
    """
    Draw LIRR logo at top-left and date + Reference # at top-right.
    Expects logo at static/letters/lirr_logo.jpg (or .png).
    """
    candidates = [
        os.path.join(settings.BASE_DIR, "static", "letters", "lirr_logo.jpg"),
        os.path.join(settings.BASE_DIR, "static", "letters", "lirr_logo.png"),
    ]
    logo_path = next((p for p in candidates if os.path.exists(p)), None)

    if logo_path:
        c.drawImage(
            ImageReader(logo_path),
            0.75 * inch,
            height - 1.3 * inch,
            width=2.8 * inch,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        c.setFont("Helvetica-Bold", 18)
        c.drawString(0.75 * inch, height - 1.0 * inch, "Long Island Rail Road")

    c.setFont("Helvetica", 11)
    c.drawRightString(
        width - 0.75 * inch, height - 1.05 * inch, timezone.now().strftime("%-m/%-d/%Y")
    )
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 0.75 * inch, height - 1.25 * inch, f"Reference # {order_id}")


def _draw_address_block(c, customer, start_y, width):
    c.setFont("Helvetica", 11)
    addr_lines = [
        customer.get("name", ""),
        customer.get("address_line1", ""),
        customer.get("address_line2", "") or None,
        f"{customer.get('city','')}, {customer.get('state','')} {customer.get('zip','')}",
        f"Email: {customer.get('email','')}",
    ]
    y = start_y
    for line in addr_lines:
        if line:
            c.drawString(0.75 * inch, y, line)
            y -= 0.18 * inch
    return y


def _draw_greeting(c, customer_first_name, y):
    c.setFont("Helvetica", 11)
    c.drawString(0.75 * inch, y, f"Dear {customer_first_name},")
    return y - 0.32 * inch


def _draw_wrapped_rich_text(c, text, x, y, width, font_size=11, leading=16):
    """
    Draw text that supports **bold** segments and paragraph breaks.
    (Simple Markdown-style bold only.)
    """
    paragraphs = text.split("\n\n")
    for p in paragraphs:

        p = re.sub(r"\s+", " ", p.strip())
        line = ""
        words = p.split(" ")

        def draw_line(ln, y_cursor):
            x_cursor = x
            parts = re.split(r"(\*\*.*?\*\*)", ln)
            for part in parts:
                if not part:
                    continue
                if part.startswith("**") and part.endswith("**"):
                    btxt = part[2:-2]
                    c.setFont("Helvetica-Bold", font_size)
                    c.drawString(x_cursor, y_cursor, btxt)
                    x_cursor += c.stringWidth(btxt, "Helvetica-Bold", font_size)
                    c.setFont("Helvetica", font_size)
                else:
                    c.setFont("Helvetica", font_size)
                    c.drawString(x_cursor, y_cursor, part)
                    x_cursor += c.stringWidth(part, "Helvetica", font_size)

        c.setFont("Helvetica", font_size)
        for w in words:
            trial = (line + " " + w).strip()
            if c.stringWidth(trial, "Helvetica", font_size) <= width:
                line = trial
            else:
                draw_line(line, y)
                y -= leading
                line = w
        if line:
            draw_line(line, y)
            y -= leading

        y -= leading / 2
    return y




@csrf_exempt
def generate_pdf(request):
    """
    Generates the denial letter PDF to media/letters and returns a download URL.
    POST JSON with the same structure as SAMPLE to override the data.
    """
    data = _load_request_data(request)
    cust = data.get("customer", {})
    first_name = (cust.get("name", "").split() or ["Customer"])[0]

    body_context = {
        "order_id": data.get("order_id"),
        "body_vars": data.get("body_vars", {}),
    }
   
    body_text = render_to_string("letters/denial_body.txt", body_context)

  
    filename = f"{timezone.now().strftime('%Y%m%d-%H%M%S')}_REFUND_DENIAL_{uuid.uuid4().hex[:8]}.pdf"
    out_dir = settings.MEDIA_ROOT / "letters"
    os.makedirs(out_dir, exist_ok=True)
    out_path = out_dir / filename

 
    c = canvas.Canvas(str(out_path), pagesize=letter)
    width, height = letter

   
    _draw_logo_and_header(c, width, height, data.get("order_id"))

    
    y = height - 2.0 * inch
    y = _draw_address_block(c, cust, y, width)

   
    y -= 0.22 * inch
    y = _draw_greeting(c, first_name, y)

   
    left_x = 0.75 * inch
    text_width = width - 1.5 * inch
    y = _draw_wrapped_rich_text(c, body_text, x=left_x, y=y, width=text_width, font_size=11, leading=16)

    
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(0.75 * inch, 0.9 * inch, "This letter was generated by the Refunds Back-Office system.")

    c.showPage()
    c.save()

    return JsonResponse(
        {
            "status": "GENERATED",
            "file": filename,
            "download_url": f"{settings.MEDIA_URL}letters/{filename}",
        }
    )
