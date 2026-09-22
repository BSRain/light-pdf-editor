"""Generated-PDF workflow benchmark through the real worker pipe, no user files."""
import argparse
import json
import math
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import pymupdf as fitz
from version import __version__


class Worker:
    def __init__(self):
        self.errors = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('pdf_worker.py'))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.reader = ThreadPoolExecutor(max_workers=1)
        self.serial = 0

    def call(self, kind, **fields):
        self.serial += 1
        started = time.perf_counter()
        self.process.stdin.write(json.dumps(dict(id=self.serial, kind=kind, **fields)) + '\n')
        self.process.stdin.flush()
        try:
            line = self.reader.submit(self.process.stdout.readline).result(timeout=120)
        except TimeoutError:
            self.process.kill()
            raise RuntimeError('Worker timed out: ' + kind)
        if not line:
            raise RuntimeError('Worker stopped: ' + kind)
        response = json.loads(line)
        if 'error' in response:
            raise RuntimeError(response['error'])
        if response['id'] != self.serial:
            raise RuntimeError('Response ID mismatch')
        return response['data'], (time.perf_counter() - started) * 1000

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.shutdown(wait=True)
        self.process.stdout.close()
        self.errors.close()


def make_fixture(path, kind):
    rng = random.Random(20260922)
    pages = 80 if kind == 'many_pages' else 3 if kind == 'large_images' else 1
    width, height = (2400, 3200) if kind == 'large_page' else (595, 842)
    with fitz.open() as doc:
        for i in range(pages):
            page = doc.new_page(width=width, height=height)
            if kind == 'large_images':
                pixels = fitz.Pixmap(fitz.csRGB, 1800, 2000, rng.randbytes(1800 * 2000 * 3), False)
                page.insert_image(page.rect, pixmap=pixels)
            lines = 140 if kind == 'large_page' else 35
            for line in range(lines):
                page.insert_text((40, 60 + 18 * line), f'Page {i+1}, line {line+1}: generated performance fixture 0123456789', fontsize=11)
        doc.save(path, deflate=True)
    return dict(pages=pages, page_width_pt=width, page_height_pt=height,
                file_mb=round(path.stat().st_size / 1048576, 3))


def summary(values):
    ordered = sorted(values)
    return dict(samples=len(values), p50_ms=round(statistics.median(values), 2),
                p95_ms=round(ordered[max(0, math.ceil(len(values) * .95) - 1)], 2),
                raw_ms=[round(v, 2) for v in values])


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', default='workflow_benchmark.json')
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    report = dict(version=__version__, platform=platform.platform(), python=platform.python_version(),
                  pymupdf=fitz.VersionBind, runs=args.runs,
                  scope='Wall time over JSON worker pipe including serialization/PNG and metadata; excludes GUI painting. Each run uses a fresh worker. Startup measured separately; OS disk cache not flushed. P95 uses nearest rank; small samples are descriptive only.',
                  memory_scope='Windows worker lifetime peak working set, includes shared pages; excludes GUI and benchmark process. Null on other systems. Not private committed memory.', fixtures={})
    with tempfile.TemporaryDirectory() as directory:
        for kind in ('many_pages', 'large_page', 'large_images'):
            path = Path(directory) / f'{kind}.pdf'
            dimensions = make_fixture(path, kind)
            timings, memory = {}, []
            def record(name, value):
                timings.setdefault(name, []).append(value)
            for _ in range(args.runs):
                start = time.perf_counter()
                worker = Worker()
                try:
                    worker.call('metrics')
                    record('startup', (time.perf_counter() - start) * 1000)
                    data, elapsed = worker.call('open', path=str(path))
                    record('open_first_page', elapsed)
                    start = time.perf_counter()
                    # Six 512px tiles cover a 1536x1024px viewport at 200%.
                    for y in (0, 256):
                        for x in (0, 256, 512):
                            clip = [x, y, min(x+256, data['width']), min(y+256, data['height'])]
                            worker.call('tile', index=0, revision=data['revision'], scale=2, clip=clip)
                    record('six_tiles_200_percent', (time.perf_counter() - start) * 1000)
                    spec = dict(x=40, y=730, width=300, height=80, text='Benchmark inserted text', size=14, color=(0, 0, 0), bold=False)
                    data, elapsed = worker.call('insert', index=0, spec=spec)
                    record('insert_with_thumbnail', elapsed)
                    obj = data['objects'][-1]
                    _, elapsed = worker.call('begin_edit', index=0, revision=data['revision'], object_id=obj['id'])
                    record('begin_reedit', elapsed)
                    data, _ = worker.call('cancel_edit', index=0)
                    _, elapsed = worker.call('save', path=str(Path(directory) / 'output.pdf'))
                    record('save', elapsed)
                    _, elapsed = worker.call('undo', index=0)
                    record('undo', elapsed)
                    _, elapsed = worker.call('redo', index=0)
                    record('redo', elapsed)
                    data, _ = worker.call('metrics')
                    memory.append(data['peak_working_set_mb'])
                finally:
                    worker.close()
            report['fixtures'][kind] = dict(**dimensions, timings={name: summary(v) for name, v in timings.items()},
                                           worker_peak_working_set_mb=memory)
            print(kind + ': ' + json.dumps(report['fixtures'][kind], ensure_ascii=False), flush=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    run()
