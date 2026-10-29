"""AST scan: report duplicate keys in the module-level dict literals."""

import ast
import pathlib

PATH = pathlib.Path(__file__).with_name("gate1_server.py")
tree = ast.parse(PATH.read_text(encoding="utf-8"))
for node in tree.body:
    if not isinstance(node, ast.Assign):
        continue
    if not isinstance(node.value, ast.Dict):
        continue
    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
    seen: dict[str, int] = {}
    for key in node.value.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        name = key.value
        seen[name] = seen.get(name, 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}
    if dupes:
        print(str(node.lineno) + " " + str(names) + " duplicates=" + str(dupes))
print("scan_done")
