import math
from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent
MAX_MB = 100

def count_lines(p):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)

def split_csv(p):
    p = Path(p)
    if p.suffix.lower() != ".csv":
        return
    n = count_lines(p)
    if n <= 1:
        return
    num_parts = max(2, math.ceil(p.stat().st_size / (MAX_MB * 1024 * 1024)))
    lines_per_part = (n - 1) // num_parts
    out_paths = [p.parent / (p.stem + "_part%d.csv" % (i + 1)) for i in range(num_parts)]
    with open(p, "r", encoding="utf-8", errors="replace") as src:
        h = src.readline()
        outs = [open(op, "w", encoding="utf-8") for op in out_paths]
        for w in outs:
            w.write(h)
        part, idx, limit = 0, 0, lines_per_part
        for line in src:
            if idx >= limit and part < num_parts - 1:
                part += 1
                limit += lines_per_part
            outs[part].write(line)
            idx += 1
        for w in outs:
            w.close()
    print("Split", p.name, "->", ", ".join(op.name for op in out_paths))

for f in sorted(DATA_DIR.glob("*.csv")):
    if "_part" in f.stem and f.stem.split("_part")[-1].isdigit():
        continue
    mb = f.stat().st_size / (1024 * 1024)
    if mb > MAX_MB:
        print("Splitting", f.name, round(mb, 1), "MB")
        split_csv(f)
    else:
        print("Skip", f.name)
