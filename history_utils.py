import csv
import io
import os

import pandas as pd


def read_history_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()

    with open(path, newline="", encoding="utf-8-sig") as history_file:
        records = [row for row in csv.reader(history_file) if row]

    if not records:
        return pd.DataFrame()

    columns = records[0]
    extra_count = (
        max(0, max(len(row) for row in records[1:]) - len(columns))
        if len(records) > 1 else 0
    )
    for index in range(extra_count):
        extra_name = f"extra_{index + 1}"
        while extra_name in columns:
            extra_name = f"_{extra_name}"
        columns.append(extra_name)

    normalized_rows = [
        row[:len(columns)] + [""] * max(0, len(columns) - len(row))
        for row in records[1:]
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(normalized_rows)
    buffer.seek(0)
    return pd.read_csv(buffer)


def append_history_rows(path, rows):
    if not rows:
        return

    existing = read_history_csv(path)
    incoming = pd.DataFrame(rows)
    columns = list(existing.columns)
    columns.extend(column for column in incoming.columns if column not in columns)

    combined = pd.concat(
        [existing.reindex(columns=columns), incoming.reindex(columns=columns)],
        ignore_index=True,
    )
    combined.to_csv(path, index=False)
