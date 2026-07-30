import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
skill_path = str(SKILL_DIR)
if skill_path in sys.path:
    sys.path.remove(skill_path)
sys.path.insert(0, skill_path)
