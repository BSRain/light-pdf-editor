"""Zoom queue cancellation and bounded progressive rendering regressions."""
import unittest
from unittest.mock import patch
import test_editor as helpers
from pdf_editor import Editor


class ZoomTests(unittest.TestCase):
    setUpClass = classmethod(helpers.QtTests.setUpClass.__func__)
    setUp = helpers.QtTests.setUp
    tearDown = helpers.QtTests.tearDown
    wait = helpers.QtTests.wait

    def settle(self):
        e=self.editor
        self.wait(lambda: not e.tile_timer.isActive() and e.client.active is None and not e.client.tiles)

    def test_view_change_drops_queued_tiles_without_discarding_edit_preview(self):
        self.settle();e=self.editor
        e.client.tiles=[dict(kind='tile',key=('old',))]
        preview=dict(kind='preview',version=123)
        e.client.preview=preview
        e.viewport_updated()
        self.assertFalse(e.client.tiles)
        self.assertFalse(e.wanted)
        self.assertIs(e.client.preview,preview)
        self.assertTrue(e.tile_timer.isActive())
        e.client.preview=None

    def test_previous_layer_survives_burst_then_disappears_when_sharp(self):
        self.settle();e=self.editor
        previous=list(e.tile_items.values())
        self.assertTrue(previous)
        e.view.set_zoom(2.3);e.schedule_tiles()
        self.assertEqual(e.fallback_tiles,previous)
        self.assertTrue(all(item.zValue()==-.5 for item in previous))
        e.view.set_zoom(3.1);e.schedule_tiles()
        self.assertEqual(e.fallback_tiles,previous)
        self.settle()
        self.assertTrue(e.wanted.issubset(e.tile_items))
        self.assertFalse(e.fallback_tiles)

    def test_oversize_previous_layer_is_not_retained(self):
        self.settle();e=self.editor
        with patch.object(Editor,'FALLBACK_TILE_LIMIT',0):
            e.view.set_zoom(2.3);e.schedule_tiles()
        self.assertFalse(e.fallback_tiles)
        self.settle()
        self.assertTrue(e.tile_items)

    def test_page_switch_discards_previous_layer(self):
        self.settle();e=self.editor
        e.view.set_zoom(2.3);e.schedule_tiles()
        self.assertTrue(e.fallback_tiles)
        e.go_to_page(1)
        self.wait(lambda: e.index==1 and not e.busy)
        self.assertFalse(e.fallback_tiles)
        self.settle()
        self.assertTrue(all(key[2]==1 for key in e.tile_items))
