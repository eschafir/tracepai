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
