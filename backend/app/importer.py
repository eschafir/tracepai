import csv
import datetime as dt
import io
import re

DATE_FORMATS = {"YYYY-MM-DD": "%Y-%m-%d", "MM/DD/YYYY": "%m/%d/%Y", "DD/MM/YYYY": "%d/%m/%Y"}
HEADER_WORDS = {
    "date": ["date", "fecha", "posted", "day"],
    "merchant": ["description", "payee", "merchant", "name", "details", "concepto", "descripcion", "memo"],
    "amount": ["amount", "importe", "monto", "value", "sum"],
    "debit": ["debit", "withdrawal", "withdrawals", "out", "cargo", "paid"],
    "credit": ["credit", "deposit", "deposits", "in", "abono", "received"],
}


def read_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]
    return [h.strip() for h in rows[0]], rows[1:]


def guess_mapping(headers: list[str]) -> dict[str, str | None]:
    mapping = {}
    for field, words in HEADER_WORDS.items():
        mapping[field] = next((h for h in headers if set(re.findall(r"[a-z]+", h.lower())) & set(words)), None)
    return mapping


def parse_date(value: str, fmt: str) -> dt.date:
    value = value.strip()
    if fmt != "YYYY-MM-DD":
        value = re.sub(r"[-.]", "/", value)
    for pattern in (DATE_FORMATS[fmt], DATE_FORMATS[fmt].replace("%Y", "%y")):
        try:
            return dt.datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"'{value}' is not a {fmt} date")


def guess_date_format(values: list[str]) -> str | None:
    def parses(value: str, fmt: str) -> bool:
        try:
            parse_date(value, fmt)
            return True
        except ValueError:
            return False

    counts = {fmt: sum(parses(v, fmt) for v in values) for fmt in DATE_FORMATS}
    best = max(counts, key=counts.get)
    return best if counts[best] else None


def parse_amount(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    negative = text.startswith("-") or text.endswith("-") or (text.startswith("(") and text.endswith(")"))
    digits = re.sub(r"[^\d.,]", "", text)
    if not re.search(r"\d", digits):
        raise ValueError(f"'{value}' is not an amount")
    last_sep = max(digits.rfind("."), digits.rfind(","))
    if last_sep != -1 and ("." in digits and "," in digits or len(digits) - last_sep - 1 in (1, 2)):
        whole, frac = digits[:last_sep], digits[last_sep + 1 :]
    else:
        whole, frac = digits, "0"
    number = float(f"{re.sub(r'[.,]', '', whole) or '0'}.{frac}")
    return -number if negative else number
