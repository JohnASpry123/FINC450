"""Load Bloomberg weekly exchange rates from the provided XLSX file.

This loader uses only the Python standard library to preserve the exact
quote values stored in the XLSX (no float coercion of quotes).
Dates are exported as ISO dates using the workbook date system.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
import posixpath
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List, Sequence


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class SheetData:
    header: List[str]
    rows: List[List[str]]


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    strings: List[str] = []
    for si in root.findall("a:si", NS):
        text_parts = [t.text or "" for t in si.findall(".//a:t", NS)]
        strings.append("".join(text_parts))
    return strings


def _read_sheet_cells(zf: zipfile.ZipFile, sheet_name: str) -> tuple[List[dict[int, str]], int]:
    xml = zf.read(sheet_name if sheet_name.startswith("xl/") else f"xl/worksheets/{sheet_name}")
    root = ET.fromstring(xml)
    shared_strings = _read_shared_strings(zf)

    rows: List[dict[int, str]] = []
    max_col = 0

    for row in root.findall(".//a:row", NS):
        row_cells: dict[int, str] = {}
        for cell in row.findall("a:c", NS):
            ref = cell.get("r")
            if not ref:
                continue
            col_idx = _column_index(ref)
            max_col = max(max_col, col_idx)
            cell_type = cell.get("t")
            value = ""
            if cell_type == "s":
                value_node = cell.find("a:v", NS)
                if value_node is not None and value_node.text is not None:
                    value = shared_strings[int(value_node.text)]
            elif cell_type == "inlineStr":
                text_parts = [t.text or "" for t in cell.findall(".//a:t", NS)]
                value = "".join(text_parts)
            else:
                value_node = cell.find("a:v", NS)
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
            if cell.find("a:f", NS) is not None and not value:
                raise ValueError(f"Formula {ref} has no cached value; refresh and save in Excel first.")
            row_cells[col_idx] = value
        rows.append(row_cells)

    return rows, max_col + 1


def load_bloomberg_weekly_exchange_rates(xlsx_path: str) -> SheetData:
    """Load the Bloomberg weekly exchange rate worksheet as strings."""
    with zipfile.ZipFile(xlsx_path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        properties = workbook.find("a:workbookPr", NS)
        date1904 = properties is not None and properties.get("date1904") in ("1", "true")
        first_sheet = workbook.find("a:sheets/a:sheet", NS)
        if first_sheet is None:
            raise ValueError("Workbook has no worksheets.")
        relation_id = first_sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relations = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relations if r.get("Id") == relation_id)
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        sheet_rows, column_count = _read_sheet_cells(zf, sheet_path.removeprefix("xl/worksheets/"))

    rows: List[List[str]] = []
    for row_cells in sheet_rows:
        row = ["" for _ in range(column_count)]
        for idx, value in row_cells.items():
            row[idx] = value
        rows.append(row)

    if not rows:
        return SheetData(header=[], rows=[])

    header = rows[0]
    data_rows = rows[1:]
    if not header or header[0] != "Date":
        raise ValueError("First worksheet must have Date in its first column.")
    epoch = dt.date(1904, 1, 1) if date1904 else dt.date(1899, 12, 30)
    for row in data_rows:
        try:
            serial = float(row[0])
        except ValueError:
            continue  # Text dates are validated by the shared analysis loader.
        if not serial.is_integer() or serial < 0:
            raise ValueError(f"Invalid Excel date serial: {row[0]}")
        row[0] = (epoch + dt.timedelta(days=int(serial))).isoformat()
    return SheetData(header=header, rows=data_rows)


def write_csv(sheet: SheetData, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(sheet.header)
        writer.writerows(sheet.rows)


def iter_dict_rows(sheet: SheetData) -> Iterable[dict[str, str]]:
    header = sheet.header
    for row in sheet.rows:
        yield {header[idx]: row[idx] for idx in range(len(header))}


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xlsx",
        default=str(Path(__file__).resolve().parent / "Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx"),
        help="Path to the XLSX file.",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "outputs/bloomberg_weekly_exchange_rates.csv"),
        help="Where to write the CSV copy.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    sheet = load_bloomberg_weekly_exchange_rates(args.xlsx)
    write_csv(sheet, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
