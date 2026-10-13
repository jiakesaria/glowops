"""Download Correlates of War files on demand, checking each one against data/cow_vars.txt.

    python cow_data.py list                 # every dataset entry and whether its sample exists
    python cow_data.py sample --all         # download 5-row samples into data/cow_samples/
    python cow_data.py check                # offline: samples match the declared variables
    python cow_data.py full cow-mida-5.0    # full file into data/cow_full/ (needs a passing sample)

Standard library only. data/cow_files.json holds the download URL, zip member, delimiter and
encoding for every id in data/cow_vars.txt.
"""

import argparse
import csv
import io
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SAMPLES = DATA / "cow_samples"
FULL = DATA / "cow_full"
SAMPLE_ROWS = 5
USER_AGENT = "Mozilla/5.0 (hypothesis-checker course project)"
FALLBACK_ENCODINGS = ("cp1252", "latin-1")


class CowDataError(Exception):
    pass


def load_catalog(root: Path = ROOT):
    """Return (datasets by id, file manifest by id); both files must list the same ids."""
    try:
        lines = (root / "data" / "cow_vars.txt").read_text(encoding="utf-8").splitlines()
        datasets = {}
        for line in filter(str.strip, lines):
            row = json.loads(line)
            datasets[row["id"]] = row
        manifest = json.loads((root / "data" / "cow_files.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        raise CowDataError(f"cannot read the CoW catalog: {exc}") from exc
    if set(datasets) != set(manifest):
        diff = sorted(set(datasets) ^ set(manifest))
        raise CowDataError(f"cow_vars.txt and cow_files.json disagree on ids: {diff}")
    return datasets, manifest


# ------------------------------------------------------------------ downloading
def download(url: str, dest: Path, cache: dict) -> Path:
    if url in cache:
        return cache[url]
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as out:
                total = response.headers.get("Content-Length")
                print(f"  downloading {url} ({int(total) / 1e6:.1f} MB)" if total else f"  downloading {url}")
                shutil.copyfileobj(response, out)
            cache[url] = dest
            return dest
        except OSError as exc:
            last = exc
    raise CowDataError(f"download failed for {url}: {last}")


def open_member(path: Path, member):
    """Open the data file as a binary stream; 'a.zip!b.csv' style members are nested zips."""
    if member is None:
        return open(path, "rb"), []
    holders = []
    archive = zipfile.ZipFile(path)
    holders.append(archive)
    while "!" in member:
        inner, member = member.split("!", 1)
        archive = zipfile.ZipFile(io.BytesIO(archive.read(inner)))
        holders.append(archive)
    return archive.open(member), holders


def read_head(path: Path, info: dict, rows: int):
    """First header plus `rows` records, decoded to text with universal newlines."""
    encodings = (info.get("encoding", "utf-8"),) + FALLBACK_ENCODINGS
    for encoding in encodings:
        stream, holders = open_member(path, info.get("member"))
        try:
            text = io.TextIOWrapper(stream, encoding=encoding, newline=None)
            reader = csv.reader(text, delimiter=info.get("delimiter", ","))
            header = next(reader)
            body = [row for _, row in zip(range(rows), reader)]
            return header, body
        except UnicodeDecodeError:
            continue
        finally:
            stream.close()
            for holder in holders:
                holder.close()
    raise CowDataError(f"cannot decode {path.name}")


# ------------------------------------------------------------------ verification
def verify_sample(dataset: dict, sample_path: Path, delimiter: str) -> list[str]:
    """Return a list of problems (empty means the sample supports the declared variables)."""
    if not sample_path.exists():
        return [f"no sample at {sample_path.relative_to(ROOT)}; run: python cow_data.py sample {dataset['id']}"]
    with sample_path.open(encoding="utf-8", newline="") as handle:
        records = list(csv.reader(handle, delimiter=delimiter))
    if len(records) < 2:
        return ["sample has no data rows"]
    header, body = [name.strip() for name in records[0]], records[1:]
    problems = []
    missing = [v["name"] for v in dataset["variables"] if v["name"].strip() not in header]
    if missing:
        problems.append(f"declared variables not in the file header: {missing}")
    if len(set(header)) != len(header):
        problems.append("duplicate column names in the header")
    if len(body) != SAMPLE_ROWS:
        problems.append(f"expected {SAMPLE_ROWS} data rows, found {len(body)}")
    bad = [i + 1 for i, row in enumerate(body) if len(row) != len(header)]
    if bad:
        problems.append(f"rows {bad} have a different number of fields than the header")
    return problems


def sample_path_for(dataset_id: str) -> Path:
    return SAMPLES / f"{dataset_id}.csv"


# ------------------------------------------------------------------ commands
def pick_ids(args, datasets):
    ids = list(datasets) if args.all or not args.ids else args.ids
    unknown = [i for i in ids if i not in datasets]
    if unknown:
        raise CowDataError(f"unknown ids: {unknown}")
    return ids


def cmd_list(args, datasets, manifest):
    for dataset_id, dataset in datasets.items():
        state = "sample ok" if not verify_sample(dataset, sample_path_for(dataset_id), manifest[dataset_id]["delimiter"]) else "no sample"
        years = dataset["years"]
        print(f"{dataset_id:45s} {years['start']}-{years['end']}  {len(dataset['variables']):3d} vars  {state}")
    return 0


def cmd_sample(args, datasets, manifest):
    SAMPLES.mkdir(parents=True, exist_ok=True)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        cache = {}
        for dataset_id in pick_ids(args, datasets):
            info = manifest[dataset_id]
            print(dataset_id)
            try:
                suffix = ".zip" if info["url"].endswith(".zip") else ".csv"
                path = download(info["url"], Path(tmp) / f"{abs(hash(info['url']))}{suffix}", cache)
                header, body = read_head(path, info, SAMPLE_ROWS)
                with sample_path_for(dataset_id).open("w", encoding="utf-8", newline="") as out:
                    writer = csv.writer(out, delimiter=info["delimiter"], lineterminator="\n")
                    writer.writerow(header)
                    writer.writerows(body)
            except (CowDataError, OSError, zipfile.BadZipFile, KeyError, StopIteration) as exc:
                print(f"  FAILED: {exc!r}")
                failures += 1
                continue
            problems = verify_sample(datasets[dataset_id], sample_path_for(dataset_id), info["delimiter"])
            print("  ok" if not problems else "  PROBLEMS: " + "; ".join(problems))
            failures += bool(problems)
    print(f"{failures} problem(s)" if failures else "all samples match the declared variables")
    return 1 if failures else 0


def cmd_check(args, datasets, manifest):
    failures = 0
    for dataset_id in pick_ids(args, datasets):
        problems = verify_sample(datasets[dataset_id], sample_path_for(dataset_id), manifest[dataset_id]["delimiter"])
        if problems:
            failures += 1
            print(f"FAIL {dataset_id}: " + "; ".join(problems))
    print(f"{failures} dataset(s) failed" if failures else f"PASS: {len(pick_ids(args, datasets))} samples match cow_vars.txt")
    return 1 if failures else 0


def extract_full(path: Path, info: dict, dest: Path) -> None:
    stream, holders = open_member(path, info.get("member"))
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(stream, out)
    finally:
        stream.close()
        for holder in holders:
            holder.close()


def cmd_full(args, datasets, manifest):
    ids = pick_ids(args, datasets)
    # The full download is only offered for datasets whose sample passed the check.
    blocked = {i: verify_sample(datasets[i], sample_path_for(i), manifest[i]["delimiter"]) for i in ids}
    blocked = {i: p for i, p in blocked.items() if p}
    if blocked:
        for dataset_id, problems in blocked.items():
            print(f"refusing {dataset_id}: " + "; ".join(problems))
        return 1
    FULL.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cache = {}
        for dataset_id in ids:
            info = manifest[dataset_id]
            dest = FULL / f"{dataset_id}.csv"
            if dest.exists() and not args.force:
                print(f"{dataset_id}: already at {dest.relative_to(ROOT)} (use --force to replace)")
                continue
            print(dataset_id)
            suffix = ".zip" if info["url"].endswith(".zip") else ".csv"
            path = download(info["url"], Path(tmp) / f"{abs(hash(info['url']))}{suffix}", cache)
            extract_full(path, info, dest)
            header, body = read_head(dest, {**info, "member": None}, SAMPLE_ROWS)
            with sample_path_for(dataset_id).open(encoding="utf-8", newline="") as handle:
                expected = next(csv.reader(handle, delimiter=info["delimiter"]))
            if header != expected:
                dest.unlink()
                raise CowDataError(f"{dataset_id}: downloaded header differs from the sample; file removed")
            print(f"  saved {dest.relative_to(ROOT)} ({dest.stat().st_size / 1e6:.1f} MB)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("list", cmd_list), ("sample", cmd_sample), ("check", cmd_check), ("full", cmd_full)):
        p = sub.add_parser(name)
        p.add_argument("ids", nargs="*", help="dataset ids (default: all)")
        p.add_argument("--all", action="store_true")
        if name == "full":
            p.add_argument("--force", action="store_true", help="replace files that already exist")
        p.set_defaults(func=func)
    args = parser.parse_args(argv)
    if args.command == "full" and not args.ids and not args.all:
        parser.error("full needs dataset ids or --all (some files are large; see data/cow_vars.txt limitations)")
    try:
        datasets, manifest = load_catalog()
        return args.func(args, datasets, manifest)
    except CowDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
