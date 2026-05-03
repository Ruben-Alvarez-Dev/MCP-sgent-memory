"""Vault Processor - Serializes and syncs vault notes."""
import os, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(os.path.expanduser("~/MCP-servers/MCP-agent-memory/data/Lx-persistent"))
LOG = VAULT / ".system" / "processor.log"

ES_FOLDERS = ["Inbox", "Decisiones", "Conocimiento", "Episodios", "Entidades", "Notas", "Personas", "Plantillas"]
EN_FOLDERS = ["inbox", "decisions", "knowledge", "episodes", "entities", "notes", "people", "templates"]
ES_TO_EN = dict(zip(ES_FOLDERS, EN_FOLDERS))

TAG_TO_FOLDER = {
    "#decision": "Decisiones", "#conocimiento": "Conocimiento",
    "#episodio": "Episodios", "#entidad": "Entidades",
    "#nota": "Notas", "#persona": "Personas",
}
TYPE_CODES = {
    "Inbox": "INBOX", "Decisiones": "DECISION", "Conocimiento": "KNOWLEDGE",
    "Episodios": "EPISODE", "Entidades": "ENTITY", "Notas": "NOTE",
    "Personas": "PERSON", "Plantillas": "TEMPLATE",
}
LAYER_MAP = {
    "Inbox": "L0", "Decisiones": "L3", "Conocimiento": "L3",
    "Episodios": "L2", "Entidades": "L3", "Notas": "L3",
    "Personas": "L3", "Plantillas": "L3",
}

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = "[{}] {}".format(ts, msg)
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
        f.write(chr(10))

def is_serialized(filename):
    return bool(re.match(r"^Ld+_[A-Z]+_d{8}Td{6}_d{5}_(ES|EN).md$", filename))

def get_next_seq(layer):
    counter_path = VAULT / ".system" / "counter.json"
    if counter_path.exists():
        counters = json.loads(counter_path.read_text())
    else:
        counters = {"next": {}}
    current = counters.get("next", {}).get(layer, 1)
    counters.setdefault("next", {})[layer] = current + 1
    counter_path.write_text(json.dumps(counters, indent=2))
    return current

def generate_name(folder, lang="ES"):
    layer = LAYER_MAP.get(folder, "L3")
    type_code = TYPE_CODES.get(folder, "NOTE")
    seq = get_next_seq(layer)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return "{}_{:05d}_{}.md".format(layer + "_" + type_code + "_" + ts, seq, lang)

def classify_by_tag(content):
    content_lower = content.lower()
    for tag, folder in TAG_TO_FOLDER.items():
        if tag in content_lower:
            return folder
    return "Notas"

def process_unserialized():
    processed = 0
    for folder in ES_FOLDERS:
        folder_path = VAULT / folder
        if not folder_path.exists():
            continue
        for f in sorted(folder_path.iterdir()):
            if not f.is_file() or not f.name.endswith(".md"):
                continue
            if is_serialized(f.name):
                continue
            if f.name.startswith(".") or f.name == "README.md":
                continue
            content = f.read_text(encoding="utf-8")
            if folder == "Inbox":
                dest_folder = classify_by_tag(content)
            else:
                dest_folder = folder
            new_name = generate_name(dest_folder, "ES")
            dest_path = VAULT / dest_folder / new_name
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(dest_path))
            log("SERIALIZE: {}/{} -> {}/{}".format(folder, f.name, dest_folder, new_name))
            en_folder = ES_TO_EN.get(dest_folder, dest_folder.lower())
            en_name = new_name.replace("_ES.md", "_EN.md")
            en_path = VAULT / en_folder / en_name
            en_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(dest_path), str(en_path))
            log("EN COPY: {}/{}".format(en_folder, en_name))
            processed += 1
    return processed

def sync_edited():
    synced = 0
    for folder in ES_FOLDERS:
        folder_path = VAULT / folder
        if not folder_path.exists():
            continue
        en_folder = ES_TO_EN.get(folder, folder.lower())
        for f in folder_path.iterdir():
            if not f.is_file() or not f.name.endswith("_ES.md"):
                continue
            en_name = f.name.replace("_ES.md", "_EN.md")
            en_path = VAULT / en_folder / en_name
            if not en_path.exists():
                shutil.copy2(str(f), str(en_path))
                log("SYNC CREATE: {}/{}".format(en_folder, en_name))
                synced += 1
            elif f.stat().st_mtime > en_path.stat().st_mtime:
                shutil.copy2(str(f), str(en_path))
                log("SYNC UPDATE: {}/{}".format(en_folder, en_name))
                synced += 1
    return synced

def clean_orphans():
    cleaned = 0
    for i, en_folder in enumerate(EN_FOLDERS):
        es_folder = ES_FOLDERS[i]
        en_path = VAULT / en_folder
        if not en_path.exists():
            continue
        for f in en_path.iterdir():
            if not f.is_file() or not f.name.endswith("_EN.md"):
                continue
            es_name = f.name.replace("_EN.md", "_ES.md")
            es_path = VAULT / es_folder / es_name
            if not es_path.exists():
                f.unlink()
                log("ORPHAN CLEAN: {}/{}".format(en_folder, f.name))
                cleaned += 1
    return cleaned

if __name__ == "__main__":
    log("=== Vault Processor Started ===")
    p = process_unserialized()
    s = sync_edited()
    c = clean_orphans()
    log("Done: serialized={}, synced={}, cleaned={}".format(p, s, c))
