"""Load Bloomberg weekly exchange rates from the provided XLSX file.

This loader uses only the Python standard library to preserve the exact
cell values stored in the XLSX (no float coercion).
"""
from __future__ import annotations

import argparse
import csv
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
    xml = zf.read(f"xl/worksheets/{sheet_name}")
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
            row_cells[col_idx] = value
        rows.append(row_cells)

    return rows, max_col + 1


def load_bloomberg_weekly_exchange_rates(xlsx_path: str) -> SheetData:
    """Load the Bloomberg weekly exchange rate worksheet as strings."""
    with zipfile.ZipFile(xlsx_path) as zf:
        sheet_rows, column_count = _read_sheet_cells(zf, "sheet1.xml")

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
    return SheetData(header=header, rows=data_rows)


def write_csv(sheet: SheetData, output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
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
        default="Bloomberg Weekly Exchange Rates since 2000 1 31 2026.xlsx",
        help="Path to the XLSX file.",
    )
    parser.add_argument(
        "--output",
        default="outputs/bloomberg_weekly_exchange_rates.csv",
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
