"""Atalho de inicio sem console (clique-duplo ou via pythonw).

Use este arquivo para abrir o Paste Cascade sem janela de terminal.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paste_cascade.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
