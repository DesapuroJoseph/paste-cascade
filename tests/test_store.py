"""Testes da logica da fila (store). Rodar: py -m unittest discover -s tests -v

Usam um APPDATA temporario e a plataforma Qt 'offscreen' (sem janela).
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from paste_cascade import config  # noqa: E402
from paste_cascade.store import ClipStore  # noqa: E402


def solid(color, w=10, h=10):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(*color))
    return img


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="cascade_test_")
        self._old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._tmp
        self.store = ClipStore()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)

    def texts(self, *names):
        for n in names:
            self.store.add_text(n)

    def queue_text(self):
        return [it.text for it in self.store.items]


class TestDedup(StoreTestCase):
    def test_images_same_size_different_content_are_kept(self):
        self.assertIsNotNone(self.store.add_image(solid((255, 0, 0))))
        self.assertIsNotNone(self.store.add_image(solid((0, 255, 0))))
        self.assertEqual(len(self.store.items), 2)

    def test_identical_consecutive_image_dropped(self):
        self.store.add_image(solid((1, 2, 3)))
        self.assertIsNone(self.store.add_image(solid((1, 2, 3))))
        self.assertEqual(len(self.store.items), 1)

    def test_text_with_different_html_is_not_duplicate(self):
        self.assertIsNotNone(self.store.add_text("a", "<b>a</b>"))
        self.assertIsNotNone(self.store.add_text("a", None))
        self.assertIsNone(self.store.add_text("a", None))


class TestCursor(StoreTestCase):
    def test_retreat(self):
        self.texts("a", "b", "c")
        self.store.cursor = 2
        self.assertTrue(self.store.retreat())
        self.assertEqual(self.store.cursor, 1)
        self.store.cursor = 0
        self.assertFalse(self.store.retreat())
        self.store.cursor = 3
        self.assertTrue(self.store.retreat())
        self.assertEqual(self.store.cursor, 2)
        self.store.settings["loop"] = True
        self.store.cursor = 0
        self.assertTrue(self.store.retreat())
        self.assertEqual(self.store.cursor, 2)

    def test_advance_and_end_sentinel(self):
        self.texts("a", "b")
        self.store.cursor = 0
        self.store.advance()
        self.store.advance()
        self.assertIsNone(self.store.peek())
        self.assertEqual(self.store.cursor, 2)

    def test_move_keeps_cursor_on_same_item(self):
        self.texts("a", "b", "c")
        self.store.cursor = 1  # "b"
        self.store.move(0, 2)  # a vai pro fim -> b, c, a
        self.assertEqual(self.store.peek().text, "b")

    def test_consume_removes_and_keeps_position(self):
        self.texts("a", "b", "c")
        self.store.cursor = 1
        self.store.consume()
        self.assertEqual(self.queue_text(), ["a", "c"])
        self.assertEqual(self.store.peek().text, "c")


class TestPinsAndLimit(StoreTestCase):
    def test_clear_keeps_pinned(self):
        self.texts("a", "b", "c")
        self.store.set_pinned([1], True)
        self.store.clear()
        self.assertEqual(self.queue_text(), ["b"])
        self.assertEqual(self.store.cursor, 0)

    def test_limit_evicts_oldest_unpinned(self):
        self.store.settings["max_items"] = 3
        self.texts("a", "b")
        self.store.set_pinned([0], True)  # "a" fixado
        self.texts("c", "d", "e")
        self.assertEqual(len(self.store.items), 3)
        self.assertIn("a", self.queue_text())  # fixado sobrevive
        self.assertEqual(self.queue_text()[-1], "e")


class TestUndo(StoreTestCase):
    def test_undo_remove_restores_position_and_cursor(self):
        self.texts("a", "b", "c", "d")
        self.store.cursor = 2  # "c"
        self.store.remove_many([0, 1])
        self.assertEqual(self.queue_text(), ["c", "d"])
        self.assertEqual(self.store.peek().text, "c")
        self.assertEqual(self.store.undo_remove(), 2)
        self.assertEqual(self.queue_text(), ["a", "b", "c", "d"])
        self.assertEqual(self.store.peek().text, "c")

    def test_undo_clear(self):
        self.texts("a", "b", "c")
        self.store.set_pinned([0], True)
        self.store.clear()
        self.assertEqual(self.queue_text(), ["a"])
        self.store.undo_remove()
        self.assertEqual(self.queue_text(), ["a", "b", "c"])

    def test_undo_keeps_items_captured_meanwhile(self):
        self.texts("a", "b")
        self.store.remove_many([0])
        self.texts("c")  # capturado depois da remocao
        self.store.undo_remove()
        self.assertEqual(sorted(self.queue_text()), ["a", "b", "c"])

    def test_nothing_to_undo(self):
        self.assertFalse(self.store.can_undo())
        self.assertEqual(self.store.undo_remove(), 0)

    def test_blob_survives_removal_until_trash_dropped(self):
        it = self.store.add_image(solid((5, 5, 5)))
        blob = config.blobs_dir() / it.image_file
        self.store.remove_many([0])
        self.assertTrue(blob.exists())  # lixeira/historico ainda referenciam
        self.store.undo_remove()
        self.assertEqual(len(self.store.items), 1)
        self.assertTrue(blob.exists())


class TestHistory(StoreTestCase):
    def test_captures_go_to_history(self):
        self.texts("a", "b")
        self.assertEqual([h.text for h in self.store.history], ["a", "b"])

    def test_history_trimmed(self):
        self.store.settings["history_max"] = 3
        self.texts("a", "b", "c", "d")
        self.assertEqual([h.text for h in self.store.history], ["b", "c", "d"])

    def test_history_disabled(self):
        self.store.settings["history_max"] = 0
        self.texts("a")
        self.assertEqual(self.store.history, [])

    def test_enqueue_from_history(self):
        self.texts("a", "b")
        self.store.clear()
        self.assertEqual(self.store.items, [])
        ids = [h.id for h in self.store.history]
        self.assertEqual(self.store.enqueue_from_history(ids), 2)
        self.assertEqual(self.queue_text(), ["a", "b"])
        self.assertEqual(len(self.store.history), 2)  # nao duplica no historico

    def test_blob_kept_while_in_history_deleted_when_gone(self):
        it = self.store.add_image(solid((9, 9, 9)))
        blob = config.blobs_dir() / it.image_file
        self.store.remove_many([0])
        self.store._trash.clear()
        self.store._collect_blobs()
        self.assertTrue(blob.exists())  # ainda no historico
        self.store.clear_history()
        self.assertFalse(blob.exists())


class TestEditAndFiles(StoreTestCase):
    def test_edit_text_resets_html(self):
        self.store.add_text("antigo", "<i>antigo</i>")
        self.assertTrue(self.store.edit_text(0, "novo"))
        it = self.store.items[0]
        self.assertEqual((it.text, it.html, it.preview), ("novo", None, "novo"))

    def test_duplicate_keeps_cursor_on_same_item(self):
        self.texts("a", "b")
        self.store.cursor = 1  # "b"
        self.store.duplicate(0)
        self.assertEqual(self.queue_text(), ["a", "a", "b"])
        self.assertEqual(self.store.peek().text, "b")

    def test_missing_files(self):
        real = os.path.join(self._tmp, "existe.txt")
        open(real, "w").close()
        gone = os.path.join(self._tmp, "sumiu.txt")
        it = self.store.add_files([real, gone])
        self.assertEqual(ClipStore.missing_files(it), [gone])
        self.assertEqual(ClipStore.missing_files(self.store.add_text("x")), [])


class TestPersistence(StoreTestCase):
    def test_roundtrip(self):
        self.texts("a", "b")
        self.store.add_text("c", "<b>c</b>")
        self.store.set_pinned([0], True)
        self.store.cursor = 1
        self.store.save()
        again = ClipStore()
        self.assertEqual([i.text for i in again.items], ["a", "b", "c"])
        self.assertTrue(again.items[0].pinned)
        self.assertEqual(again.items[2].html, "<b>c</b>")
        self.assertEqual(again.cursor, 1)
        self.assertEqual(len(again.history), 3)

    def test_ids_do_not_collide_after_reload(self):
        self.texts("a")
        again = ClipStore()
        again.add_text("b")
        ids = [i.id for i in again.items] + [h.id for h in again.history]
        self.assertEqual(len(ids), len(set(ids)))

    def test_corrupt_items_file_is_quarantined(self):
        self.texts("a")
        config.items_path().write_text("{ nao e json", encoding="utf-8")
        again = ClipStore()
        self.assertEqual(again.items, [])
        self.assertTrue(list(config.data_dir().glob("items.corrupt-*.json")))


class TestLegacyMigration(StoreTestCase):
    def test_old_data_dir_is_migrated_once(self):
        old = os.path.join(self._tmp, config.LEGACY_APP_NAME)
        os.makedirs(old)
        with open(os.path.join(old, "items.json"), "w", encoding="utf-8") as f:
            f.write('{"version": "1.0.0", "cursor": 0, "next_id": 5, "items": '
                    '[{"id": 4, "kind": "text", "text": "antigo", "preview": "antigo"}]}')
        shutil.rmtree(os.path.join(self._tmp, config.APP_NAME), ignore_errors=True)
        again = ClipStore()
        self.assertEqual([i.text for i in again.items], ["antigo"])
        self.assertTrue((config.data_dir() / "items.json").exists())


if __name__ == "__main__":
    unittest.main()
