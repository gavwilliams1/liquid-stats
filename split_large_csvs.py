"""
Split large CSVs into parts under 100MB for GitHub (100MB file limit).
Each part has the same column headings. Original file is left unchanged.
Use name_part1.csv, name_part2.csv, ... in the repo; dashboard load_csv() supports these.
"""
import csv
import io
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
MAX_PART_BYTES = 95 * 1024 * 1024  # 95 MB to stay under 100MB
MIN_SIZE_TO_SPLIT = 100 * 1024 * 1024  # Only split files >= 100MB


def get_part_files(basedir: Path, base_name: str):
    """Return sorted list of existing part files for this base name."""
    parts = list(basedir.glob(f"{base_name}_part*.csv"))
    return sorted(
        parts,
        key=lambda p: int(m.group(1)) if (m := re.search(r"_part(\d+)\.csv$", p.name)) else 0,
    )


def split_one(basedir: Path, path: Path, max_part_bytes: int = MAX_PART_BYTES) -> bool:
    """Split path into parts under max_part_bytes. Each part has the same header. Returns True if split was done."""
    base_name = path.stem
    size_mb = path.stat().st_size / (1024 * 1024)
    if path.stat().st_size < MIN_SIZE_TO_SPLIT:
        print(f"  Skip {path.name} ({size_mb:.1f} MB < 100 MB)")
        return False

    # Remove existing part files for this base name
    existing = get_part_files(basedir, base_name)
    for p in existing:
        p.unlink()
        print(f"  Removed {p.name}")

    part_num = 1
    part_path = basedir / f"{base_name}_part{part_num}.csv"
    part_file = None
    part_bytes = 0
    total_rows = 0

    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            buf = io.StringIO()
            csv.writer(buf).writerow(header)
            header_bytes = len(buf.getvalue().encode("utf-8"))

            part_file = open(part_path, "w", encoding="utf-8", newline="")
            writer = csv.writer(part_file)
            writer.writerow(header)
            part_bytes = header_bytes

            for row in reader:
                buf = io.StringIO()
                csv.writer(buf).writerow(row)
                row_bytes = len(buf.getvalue().encode("utf-8"))
                if part_bytes + row_bytes > max_part_bytes and part_bytes > 0:
                    part_file.close()
                    part_num += 1
                    part_path = basedir / f"{base_name}_part{part_num}.csv"
                    part_file = open(part_path, "w", encoding="utf-8", newline="")
                    writer = csv.writer(part_file)
                    writer.writerow(header)
                    part_bytes = header_bytes
                writer.writerow(row)
                part_bytes += row_bytes
                total_rows += 1
                if total_rows % 200_000 == 0:
                    print(f"  ... {total_rows:,} rows")
    except Exception:
        if part_file and not part_file.closed:
            part_file.close()
        raise
    finally:
        if part_file and not part_file.closed:
            part_file.close()

    parts_created = part_num
    print(f"  Split into {parts_created} part(s): {base_name}_part1.csv ... {base_name}_part{parts_created}.csv ({total_rows:,} rows)")
    return True


def main():
    basedir = DATA_DIR
    csv_files = sorted(basedir.glob("*.csv"))
    to_split = [p for p in csv_files if p.stat().st_size >= MIN_SIZE_TO_SPLIT]
    if not to_split:
        print("No CSV files >= 100 MB found. Nothing to split.")
        return
    print(f"Splitting {len(to_split)} file(s) (>= 100 MB) into parts < 100 MB.\n")
    for path in to_split:
        print(path.name)
        split_one(basedir, path)
        print()
    print("Done. Use the _part1, _part2, ... files in git; you can remove the originals from the repo if desired.")


if __name__ == "__main__":
    main()
