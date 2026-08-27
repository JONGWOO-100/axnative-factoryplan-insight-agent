"""프로젝트 루트를 sys.path에 올려 `insight_agent` 패키지를 테스트에서 import 가능하게 한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
