"""Filesystem and runtime configuration."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAVE_PATH = os.path.join(BASE_DIR, "saves", "slot1.json")
