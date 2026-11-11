"""Smoke test da janela (offscreen): constroi, popula, troca de pagina e re-tema."""
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

from paste_cascade import theme  # noqa: E402
from paste_cascade.engine import CascadeEngine  # noqa: E402
from paste_cascade.main_window import MainWindow  # noqa: E402
from paste_cascade.store import ClipStore  # noqa: E402


class TestWindow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="cascade_ui_")
        self._old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._tmp
        _app.setStyle("Fusion")
        theme.apply(_app)
        self.store = ClipStore()
        self.engine = CascadeEngine(self.store)
        self.win = MainWindow(self.store, self.engine)

    def tearDown(self):
        self.win.close()
        if self._old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_populates_both_lists(self):
        img = QImage(30, 20, QImage.Format.Format_ARGB32)
        img.fill(QColor(10, 120, 200))
        self.store.add_text("primeiro item")
        self.store.add_text("segundo", "<b>segundo</b>")
        self.store.add_image(img)
        self.store.add_files([os.path.join(self._tmp, "inexistente.txt")])
        self.assertEqual(self.win.q_list.count(), 4)
        self.assertEqual(self.win.h_list.count(), 4)
        self.assertIn("Próximo", self.win.chip.text())

    def test_remove_and_undo_through_window(self):
        self.store.add_text("a")
        self.store.add_text("b")
        self.win.q_list.item(0).setSelected(True)
        self.win._remove_selected()
        self.assertEqual(self.win.q_list.count(), 1)
        self.assertTrue(self.win.btn_undo.isEnabled())
        self.win._undo()
        self.assertEqual(self.win.q_list.count(), 2)

    def test_pages_filter_and_theme(self):
        self.store.add_text("banana")
        self.store.add_text("maçã")
        self.win._switch_page(MainWindow.PAGE_HISTORY)
        self.assertEqual(self.win.lbl_title.text(), "Histórico")
        self.win.search.setText("ban")
        hidden = [self.win.h_list.item(i).isHidden() for i in range(self.win.h_list.count())]
        self.assertEqual(sorted(hidden), [False, True])
        self.win.search.clear()
        theme.apply(_app)
        self.win.retheme()
        self.win._toggle_nav()
        self.win._toggle_nav()

    def test_theme_modes(self):
        self.assertEqual(theme.apply(_app, "dark").name, "dark")
        self.assertEqual(theme.apply(_app, "light").name, "light")
        self.assertIn(theme.apply(_app, "system").name, ("light", "dark"))
        self.assertIn(theme.apply(_app, "valor-invalido").name, ("light", "dark"))
        # o seletor das Configuracoes guarda o modo escolhido
        from paste_cascade.settings_dialog import SettingsDialog
        self.store.settings["theme"] = "dark"
        dlg = SettingsDialog(self.store, None, self.win)
        self.assertEqual(dlg.combo_theme.currentData(), "dark")
        dlg.combo_theme.setCurrentIndex(dlg.combo_theme.findData("light"))
        dlg.accept()
        self.assertEqual(self.store.settings["theme"], "light")
        theme.apply(_app, "system")

    def test_render_both_themes(self):
        self.store.add_text("texto de exemplo")
        self.win.show()
        for t in (theme.LIGHT, theme.DARK):
            _app.setStyleSheet(theme.build_qss(t))
            theme._current = t
            self.win.retheme()
            pm = self.win.grab()
            self.assertFalse(pm.isNull())


if __name__ == "__main__":
    unittest.main()
