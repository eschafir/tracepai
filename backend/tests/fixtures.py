"""Generates test documents in code so they are reproducible and nothing binary lives in the repo."""

import io
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def text_image(lines: list[str], width: int = 620, size: int = 28, spacing: int = 46) -> Image.Image:
    image = Image.new("RGB", (width, 60 + spacing * len(lines)), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((30, 30 + i * spacing), line, fill="black", font=font(size))
    return image


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def pdf(pages: list[Image.Image]) -> bytes:
    out = io.BytesIO()
    pages[0].save(out, format="PDF", save_all=True, append_images=pages[1:], resolution=100)
    return out.getvalue()


RECEIPT_LINES = [
    "BLUE BOTTLE COFFEE",
    "66 Mint St, San Francisco",
    "09/21/2026 08:14",
    "",
    "Latte              5.75",
    "Croissant          4.50",
    "SUBTOTAL          10.25",
    "TAX                0.90",
    "TOTAL             11.15",
    "VISA ****4242     11.15",
]


def receipt() -> bytes:
    return png(text_image(RECEIPT_LINES))


def phone_photo_receipt() -> bytes:
    """The receipt as a slightly rotated, blurred JPEG on a gray table, like a phone photo."""
    paper = text_image(
        ["TRADER JOE'S #552", "3 New Montgomery St", "Date: 2026-09-18", "", "Bananas            1.96",
         "Almond milk        3.49", "Sourdough          4.99", "Subtotal          10.44", "Tax                0.00",
         "Total             10.44", "Paid DEBIT        10.44"]
    )
    table = Image.new("RGB", (paper.width + 160, paper.height + 160), (118, 112, 104))
    table.paste(paper, (80, 80))
    photo = table.rotate(4, expand=True, fillcolor=(118, 112, 104)).filter(ImageFilter.GaussianBlur(0.8))
    out = io.BytesIO()
    photo.save(out, format="JPEG", quality=70)
    return out.getvalue()


def spanish_ticket() -> bytes:
    return png(text_image(["MERCADONA S.A.", "C/ Colon 12, Valencia", "Fecha: 21/09/2026", "", "Pan          1,20",
                           "Leche        0,95", "Tomates      2,30", "Queso       19,00", "TOTAL      23,45 EUR"]))


def invoice_pdf() -> bytes:
    page = text_image(
        ["INVOICE #2026-114", "Northwind Web Hosting LLC", "Invoice date: 2026-09-10", "Bill to: J. Doe", "",
         "Business hosting plan      120.00", "Domain renewal              18.00", "Subtotal                   138.00",
         "Tax (8%)                    11.04", "TOTAL DUE                  149.04", "", "Payment due: 2026-10-10"],
        width=820,
    )
    return pdf([page])


STATEMENT_ROWS = [
    # date, description, withdrawal, deposit
    ("2026-08-01", "ACME CORP PAYROLL", None, 5200.00),
    ("2026-08-01", "PARKVIEW APTS RENT", 1450.00, None),
    ("2026-08-03", "SAFEWAY #1234", 86.42, None),
    ("2026-08-05", "NETFLIX.COM", 15.49, None),
    ("2026-08-07", "UBER *TRIP", 24.10, None),
    ("2026-08-09", "ATM WITHDRAWAL", 200.00, None),
    ("2026-08-12", "SPOTIFY", 11.99, None),
    ("2026-08-14", "ZELLE FROM J SMITH", None, 120.00),
    ("2026-08-16", "SHELL OIL 5521", 48.75, None),
    ("2026-08-18", "PG&E ELECTRIC", 97.36, None),
    ("2026-08-20", "WHOLE FOODS MKT", 132.08, None),
    ("2026-08-21", "BLUE BOTTLE COFFEE", 11.15, None),
    ("2026-08-23", "AMAZON MKTP", 56.48, None),
    ("2026-08-25", "COMCAST CABLE", 79.99, None),
    ("2026-08-27", "TARTINE BAKERY", 23.60, None),
    ("2026-08-29", "IKEA EMERYVILLE", 210.30, None),
]


def statement_pdf() -> bytes:
    """A two-page checking statement with opening and closing balance rows that must be skipped."""
    balance = 2450.00
    lines = [("2026-08-01", "Opening balance", "", "", f"{balance:,.2f}")]
    for date, description, out, deposit in STATEMENT_ROWS:
        balance += (deposit or 0) - (out or 0)
        lines.append((date, description, f"{out:,.2f}" if out else "", f"{deposit:,.2f}" if deposit else "", f"{balance:,.2f}"))
    lines.append(("2026-08-31", "Closing balance", "", "", f"{balance:,.2f}"))

    pages = []
    for number, chunk in enumerate([lines[:9], lines[9:]], start=1):
        page = Image.new("RGB", (1100, 700), "white")
        draw = ImageDraw.Draw(page)
        draw.text((40, 30), "FIRST CITY BANK - Checking account statement", fill="black", font=font(26))
        draw.text((40, 70), f"Account ****5521   Period: Aug 1 - Aug 31, 2026   Page {number} of 2", fill="black", font=font(20))
        columns = [40, 200, 640, 820, 960]
        for x, title in zip(columns, ["Date", "Description", "Withdrawals", "Deposits", "Balance"]):
            draw.text((x, 130), title, fill="black", font=font(22))
        for i, row in enumerate(chunk):
            for x, value in zip(columns, row):
                draw.text((x, 175 + i * 50), value, fill="black", font=font(20))
        pages.append(page)
    return pdf(pages)


def not_a_document() -> bytes:
    """A landscape-like picture with no text."""
    rng = random.Random(7)
    image = Image.new("RGB", (640, 420), (135, 190, 235))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 280, 640, 420), fill=(70, 140, 60))
    draw.ellipse((470, 40, 560, 130), fill=(250, 220, 90))
    for _ in range(12):
        x = rng.randint(0, 600)
        draw.polygon([(x, 280), (x + 20, 200), (x + 40, 280)], fill=(40, 100, 45))
    return png(image)
