
from dataclasses import dataclass, field, asdict
from pathlib import Path
import tomllib, json
from typing import Any, Dict


@dataclass
class LinkedStore:
    # uuid -> {code, expires (unix ts), name}
    pending: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # uuid -> discord_id
    links: Dict[str, str] = field(default_factory=dict)

    @staticmethod
    def load(path: Path) -> "LinkedStore":
        if not path.exists():
            store = LinkedStore()
            store.save(path)
            return store
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return LinkedStore(
            pending=dict(data.get("pending", {})),
            links=dict(data.get("links", {})),
        )

    def save(self, path: Path):
        def _quote(s: str) -> str:
            return json.dumps(s)

        def _val(v) -> str:
            if isinstance(v, bool): return "true" if v else "false"
            if isinstance(v, (int, float)): return str(v)
            if isinstance(v, str): return _quote(v)
            if isinstance(v, dict):
                return "{" + ", ".join(f"{k} = {_val(vv)}" for k, vv in v.items()) + "}"
            if isinstance(v, list):
                return "[" + ", ".join(_val(x) for x in v) + "]"
            return _quote(str(v))

        data = asdict(self)
        lines: list[str] = []
        for k, v in data.items():
            lines.append(f"[{k}]")
            for kk, vv in v.items():
                lines.append(f"{kk} = {_val(vv)}")
            lines.append("")
        out = "\n".join(lines).rstrip() + "\n"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(path)
