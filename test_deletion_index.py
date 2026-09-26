"""Spatial filtering must never omit a protected intersecting glyph."""
import random
import unittest
import pymupdf as fitz
from pdf_core import CharacterRectIndex


class DeletionIndexTests(unittest.TestCase):
    def test_candidates_match_full_scan_with_negative_and_large_boxes(self):
        rng = random.Random(934)
        rects = []
        for _ in range(1000):
            x, y = rng.uniform(-200, 900), rng.uniform(-200, 1800)
            rects.append(fitz.Rect(x, y, x + rng.uniform(0, 80), y + rng.uniform(0, 90)))
        rects.extend([fitz.Rect(-100, -10000, 100, 10000), fitz.Rect(0, 32, 40, 64),
                      fitz.Rect(0, 32, 0, 32)])
        index = CharacterRectIndex(rects)
        queries = rects[::5] + [fitz.Rect(-1000, -100000, 2000, 100000)]
        for query in queries:
            expected = [tuple(r) for r in rects if query.intersects(r)]
            actual = [tuple(r) for r in index.candidates(query) if query.intersects(r)]
            self.assertEqual(actual, expected)
        self.assertLessEqual(sum(map(len, index.bands.values())), len(rects) * 64)

    def test_dense_page_drops_distant_rows_and_preserves_boundary_neighbors(self):
        rects = [fitz.Rect(col * 6, row * 13, col * 6 + 6, row * 13 + 12)
                 for row in range(100) for col in range(60)]
        index = CharacterRectIndex(rects)
        query = fitz.Rect(0, 31.5, 8, 32.5)
        candidates = index.candidates(query)
        self.assertLess(len(candidates), len(rects) // 10)
        self.assertEqual([tuple(r) for r in candidates if query.intersects(r)],
                         [tuple(r) for r in rects if query.intersects(r)])


if __name__ == '__main__':
    unittest.main()
