from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

CFG_VAR_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*$")
CFG_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_]\w*)\s*=\s*(.+?)(?:\s+parent\s+([A-Za-z_]\w*))?\s*$")
CFG_DIR_RE = re.compile(r"""^\s*(?:\w+\s+)*mkdir\s+path\s+([A-Za-z_]\w*)\s*=\s*(\S+)(?:.*?\bclass_level\s+([A-Za-z_]\w*))?.*$""", re.X)
CFG_FILE_RE = re.compile(r"""^\s*(?:\w+\s+)*path\s+file\s+([A-Za-z_]\w*)\s*=\s*(\S+)\s+dir\s+([A-Za-z_]\w*)(?:.*?\bclass_level\s+([A-Za-z_]\w*))?.*$""", re.X)
DOLLAR_RE = re.compile(r"\$([A-Za-z_]\w*)")
AT_RE = re.compile(r"@([A-Za-z_]\w*)")

META_KEY_RE = re.compile(r"^\s*!key\s+([A-Za-z_]\w*)\s+(.*?)\s*$")
META_CONFIG_RE = re.compile(r"^\s*!config\s+(\S+)\s*$")
META_CLASS_RE = re.compile(r"^\s*([^\s#]+)\s+class\s+([A-Za-z_]\w*)\s*$")
META_PARENT_RE = re.compile(r"^\s*([^\s#]+)\s+parent\s+([^\s#]+)\s*$")
META_PROP_RE = re.compile(r"^\s*([^\s#]+)\s+([A-Za-z_]\w*)\s+(.*?)\s*$")

def _strip_comments(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[0]
    return line

def _expand_dollars(s: str, varmap: Dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return varmap.get(key, m.group(0))
    return DOLLAR_RE.sub(repl, s)

def _norm_join(*parts: str) -> str:
    return os.path.normpath(os.path.join(*parts))

@dataclass
class ClassDef:
    name: str
    display: str
    parent: Optional[str] = None

@dataclass
class DirTemplate:
    name: str
    template: str
    class_level: Optional[str] = None
    def tokens(self) -> Set[str]:
        return set(AT_RE.findall(self.template))

@dataclass
class FileTemplate:
    name: str
    tpl: str
    dir_ref: str
    class_level: Optional[str] = None
    def tokens(self) -> Set[str]:
        return set(AT_RE.findall(self.tpl))

@dataclass
class PipelineCfg:
    variables: Dict[str, str] = field(default_factory=dict)
    classes: Dict[str, ClassDef] = field(default_factory=dict)   # class -> def
    child_classes: Dict[str, List[str]] = field(default_factory=dict)  # class -> [child classes]
    dirs: Dict[str, DirTemplate] = field(default_factory=dict)   # dir var -> template
    files: Dict[str, FileTemplate] = field(default_factory=dict) # file key -> template

    @classmethod
    def parse(cls, text: str, extra_vars: Optional[Dict[str, str]] = None) -> "PipelineCfg":
        variables: Dict[str, str] = {}
        classes: Dict[str, ClassDef] = {}
        dirs: Dict[str, DirTemplate] = {}
        files: Dict[str, FileTemplate] = {}

        if extra_vars:
            variables.update(extra_vars)

        for raw in text.splitlines():
            line = _strip_comments(raw).strip()
            if not line:
                continue

            m = CFG_VAR_RE.match(line)
            if m:
                variables[m.group(1)] = m.group(2)
                continue

            m = CFG_CLASS_RE.match(line)
            if m:
                name, disp, parent = m.group(1), m.group(2).strip(), m.group(3)
                classes[name] = ClassDef(name, disp, parent)
                continue

            m = CFG_DIR_RE.match(line)
            if m:
                name, tpl, lvl = m.group(1), m.group(2), m.group(3)
                dirs[name] = DirTemplate(name, tpl, lvl)
                continue

            m = CFG_FILE_RE.match(line)
            if m:
                name, tpl, dir_ref, lvl = m.group(1), m.group(2), m.group(3), m.group(4)
                files[name] = FileTemplate(name, tpl, dir_ref, lvl)
                continue

        child_classes: Dict[str, List[str]] = {}
        for c in classes.values():
            if c.parent:
                child_classes.setdefault(c.parent, []).append(c.name)

        return cls(variables, classes, child_classes, dirs, files)

    @classmethod
    def from_file(cls, path: str, extra_vars: Optional[Dict[str, str]] = None) -> "PipelineCfg":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return cls.parse(f.read(), extra_vars=extra_vars)

@dataclass
class Instance:
    name: str
    class_name: str
    parents: List[str] = field(default_factory=list)  # parent instance names
    props: Dict[str, str] = field(default_factory=dict)

@dataclass
class Meta:
    keys: Dict[str, str] = field(default_factory=dict)  # !key entries -> become $vars
    config_path: Optional[str] = None
    instances: Dict[str, Instance] = field(default_factory=dict) # instance name -> Instance
    by_class: Dict[str, List[str]] = field(default_factory=dict) # class -> [instance names]

    @classmethod
    def parse(cls, text: str) -> "Meta":
        keys: Dict[str, str] = {}
        config_path: Optional[str] = None
        instances: Dict[str, Instance] = {}

        for raw in text.splitlines():
            line = _strip_comments(raw).strip()
            if not line:
                continue

            m = META_CONFIG_RE.match(line)
            if m:
                config_path = m.group(1)
                continue

            m = META_KEY_RE.match(line)
            if m:
                keys[m.group(1)] = m.group(2)
                continue

            m = META_CLASS_RE.match(line)
            if m:
                inst, clsname = m.group(1), m.group(2)
                inst_obj = instances.get(inst) or Instance(inst, clsname, [], {})
                inst_obj.class_name = clsname
                instances[inst] = inst_obj
                continue

            m = META_PARENT_RE.match(line)
            if m:
                inst, parent_inst = m.group(1), m.group(2)
                inst_obj = instances.get(inst) or Instance(inst, class_name="", parents=[], props={})
                inst_obj.parents.append(parent_inst)
                instances[inst] = inst_obj
                continue

            m = META_PROP_RE.match(line)
            if m:
                inst, key, val = m.group(1), m.group(2), m.group(3)
                inst_obj = instances.get(inst) or Instance(inst, class_name="", parents=[], props={})
                inst_obj.props[key] = val
                instances[inst] = inst_obj
                continue

        by_class: Dict[str, List[str]] = {}
        for inst, obj in instances.items():
            if obj.class_name:
                by_class.setdefault(obj.class_name, []).append(inst)

        return cls(keys, config_path, instances, by_class)

    @classmethod
    def from_file(cls, path: str) -> "Meta":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return cls.parse(f.read())

class LapResolver:
    """
    Loads CFG + META, builds a full index of absolute file paths.
    - Index key: cfg file key (e.g., "model_selection_plot_out_file")
    - Index value: list of dicts with {"path": <abs-path>, "placeholders": {<ph>:<value>}, "class_level": <lvl>, "source": "template|override"}
    Supports filtering by placeholders.
    """

    def __init__(self, cfg: PipelineCfg, meta: Meta, cwd: Optional[str] = None):
        self.cfg = cfg
        self.meta = meta
        self.cwd = cwd or os.getcwd()

        self.varmap: Dict[str, str] = dict(cfg.variables)
        self.varmap.update(meta.keys)

        self.concrete_dirs: Dict[str, str] = {}
        self._bootstrap_concrete_dirs()

        self.ancestry: Dict[str, Set[str]] = self._compute_ancestry()

        self.index: Dict[str, List[Dict]] = {}
        self._build_index()

    def _bootstrap_concrete_dirs(self) -> None:
        changed = True
        for _ in range(8):
            if not changed:
                break
            changed = False
            for name, d in self.cfg.dirs.items():
                if name in self.concrete_dirs:
                    continue
                expanded = _expand_dollars(d.template, {**self.varmap, **self.concrete_dirs})
                if '@' in expanded:
                    # Just add the variable to the varmap everything before the @
                    self.varmap[name] = expanded
                    continue
                if not os.path.isabs(expanded):
                    expanded = _norm_join(self.cwd, expanded)
                self.concrete_dirs[name] = expanded
                self.varmap[name] = expanded
                changed = True

    def _compute_ancestry(self) -> Dict[str, Set[str]]:
        parents = {inst: set(obj.parents) for inst, obj in self.meta.instances.items()}
        closure: Dict[str, Set[str]] = {inst: set(p) for inst, p in parents.items()}
        changed = True
        for _ in range(64):
            if not changed:
                break
            changed = False
            for inst in list(closure.keys()):
                new_set = set(closure[inst])
                for p in list(closure[inst]):
                    new_set |= closure.get(p, set())
                if len(new_set) > len(closure[inst]):
                    closure[inst] = new_set
                    changed = True
        return closure

    def _ph_needed_for_file(self, f, d) -> Set[str]:
        toks = set()
        toks |= f.tokens()
        toks |= d.tokens()
        return set('@' + t for t in toks)

    def _expand_placeholders(self, s: str, ph: Dict[str, str]) -> str:
        s = _expand_dollars(s, {**self.varmap, **self.concrete_dirs})
        def repl(m: re.Match) -> str:
            key = '@' + m.group(1)
            if key in ph:
                return ph[key]
            return m.group(0)
        return AT_RE.sub(repl, s)

    def _resolve_dir(self, d, ph: Dict[str, str]) -> Optional[str]:
        s = self._expand_placeholders(d.template, ph)
        if '@' in s:
            return None
        if not os.path.isabs(s):
            s = _norm_join(self.cwd, s)
        return s

    def _contexts_for_class_level(self, class_level: Optional[str]) -> List[Dict[str, str]]:
        contexts: List[Dict[str, str]] = []
        if not class_level:
            return [dict()]
        inst_names = self.meta.by_class.get(class_level, [])
        for inst in inst_names:
            ctx = self._build_context_from_instance(inst)
            if ctx:
                contexts.append(ctx)
        return contexts

    def _build_context_from_instance(self, inst: str) -> Optional[Dict[str, str]]:
        if inst not in self.meta.instances:
            return None
        ctx: Dict[str, str] = {}
        inst_obj = self.meta.instances[inst]
        cls = inst_obj.class_name
        if cls:
            ctx[f"@{cls}"] = inst
        to_visit = list(inst_obj.parents)
        seen: Set[str] = set()
        while to_visit:
            p = to_visit.pop(0)
            if p in seen:
                continue
            seen.add(p)
            pobj = self.meta.instances.get(p)
            if not pobj:
                continue
            if pobj.class_name and f"@{pobj.class_name}" not in ctx:
                ctx[f"@{pobj.class_name}"] = p
            to_visit.extend(pobj.parents)
        return ctx

    def _build_index(self) -> None:
        for fname, ftemp in self.cfg.files.items():
            dtemp = self.cfg.dirs.get(ftemp.dir_ref)
            if not dtemp:
                continue

            required_ph = self._ph_needed_for_file(ftemp, dtemp)
            contexts = self._contexts_for_class_level(ftemp.class_level)

            for inst_name, inst in self.meta.instances.items():
                if fname in inst.props:
                    path = _expand_dollars(inst.props[fname], {**self.varmap, **self.concrete_dirs})
                    if not os.path.isabs(path):
                        path = _norm_join(self.cwd, path)
                    ctx = self._build_context_from_instance(inst_name) or {}
                    self.index.setdefault(fname, []).append({
                        "path": path,
                        "placeholders": ctx,
                        "class_level": ftemp.class_level,
                        "source": "raw",
                    })

            for base_ctx in contexts:
                full_dir = self._resolve_dir(dtemp, base_ctx)
                if full_dir is None:
                    continue
                fname_expanded = self._expand_placeholders(ftemp.tpl, base_ctx)
                if '@' in fname_expanded:
                    continue
                full_path = _norm_join(full_dir, fname_expanded)
                self.index.setdefault(fname, []).append({
                    "path": full_path,
                    "placeholders": dict(base_ctx),
                    "class_level": ftemp.class_level,
                    "source": "out",
                })

    def get(self, file_key: str, source: Optional[str] = None, **filters: str) -> List[str]:
        if file_key not in self.index:
            return []
        norm_filters = { (f"@{k}" if not k.startswith("@") else k): v for k, v in filters.items() }
        out: List[str] = []
        for rec in self.index[file_key]:
            ctx = rec["placeholders"]
            if all(ctx.get(k) == v for k, v in norm_filters.items()):
                if source and rec["source"] != source:
                    continue
                out.append(rec["path"])
        return out

    def records(self, file_key: str, **filters: str) -> List[Dict]:
        if file_key not in self.index:
            return []
        norm_filters = { (f"@{k}" if not k.startswith("@") else k): v for k, v in filters.items() }
        out: List[Dict] = []
        for rec in self.index[file_key]:
            ctx = rec["placeholders"]
            if all(ctx.get(k) == v for k, v in norm_filters.items()):
                out.append(rec)
        return out