"""pytest 공통 설정. sys.path에 41r/ 추가."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
