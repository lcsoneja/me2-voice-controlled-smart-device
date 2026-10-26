import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
p = Path(r'C:/Users/Leandro/AppData/Local/Temp/pi-subagents-user-Leandro/async-subagent-runs/08b78380-028e-48fd-9caf-bc8f0193c26b/output-0.log')
text = p.read_text(encoding="utf-8", errors="replace")
print("bytes:", len(text))
print(text[-2500:])
