"""Dense synthetic page, measured through the real PDF worker pipe."""
import argparse
import json
from pathlib import Path
import statistics
import tempfile
import pymupdf as fitz
from benchmark_workflows import Worker
from version import __version__


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    timings = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'dense.pdf'
        with fitz.open() as doc:
            page = doc.new_page(width=640, height=900)
            for row in range(60):
                page.insert_text((30, 30 + row * 13), '0123456789' * 6, fontsize=10, fontname='cour')
            doc.save(path)
        for _ in range(args.runs):
            worker = Worker()
            try:
                before, _ = worker.call('open', path=str(path))
                chars = before['characters']
                ids = [c['id'] for c in chars if c['bbox'][0] < 89]
                after, elapsed = worker.call('delete_chars', index=0, revision=before['revision'], ids=ids)
                selected = set(ids)
                expected = [c['text'] for c in chars if c['id'] not in selected]
                assert [c['text'] for c in after['characters']] == expected
                restored, _ = worker.call('undo', index=0)
                assert restored['characters'] == chars
                timings.append(round(elapsed, 2))
            finally:
                worker.close()
    report = dict(version=__version__, pymupdf=fitz.VersionBind, characters=len(chars),
                  deleted=len(ids), runs_ms=timings, median_ms=round(statistics.median(timings), 2),
                  note='Synthetic dense page; full worker deletion response including safety checks and thumbnail. Local timings, not a general speed guarantee.')
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()

