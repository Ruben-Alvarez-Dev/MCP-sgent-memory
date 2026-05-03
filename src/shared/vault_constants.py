"""Vault folder constants and bilingual mapping.

Code ALWAYS uses EN constants (FOLDER_DECISIONS, etc.).
Disk presents ES folders for Obsidian user (Decisiones/, etc.).
This module is the SINGLE SOURCE OF TRUTH for the mapping.
"""

# === INTERNAL CONSTANTS (code uses these) ===
FOLDER_INBOX = "inbox"
FOLDER_DECISIONS = "decisions"
FOLDER_KNOWLEDGE = "knowledge"
FOLDER_EPISODES = "episodes"
FOLDER_ENTITIES = "entities"
FOLDER_NOTES = "notes"
FOLDER_PEOPLE = "people"
FOLDER_TEMPLATES = "templates"

# All folders in English (canonical)
ALL_FOLDERS = [
    FOLDER_INBOX,
    FOLDER_DECISIONS,
    FOLDER_KNOWLEDGE,
    FOLDER_EPISODES,
    FOLDER_ENTITIES,
    FOLDER_NOTES,
    FOLDER_PEOPLE,
    FOLDER_TEMPLATES,
]

# === BILINGUAL MAPPING ===
# English (canonical) -> Spanish (user-facing disk folders)
EN_TO_ES = {
    FOLDER_INBOX: "Inbox",
    FOLDER_DECISIONS: "Decisiones",
    FOLDER_KNOWLEDGE: "Conocimiento",
    FOLDER_EPISODES: "Episodios",
    FOLDER_ENTITIES: "Entidades",
    FOLDER_NOTES: "Notas",
    FOLDER_PEOPLE: "Personas",
    FOLDER_TEMPLATES: "Plantillas",
}

# Spanish (disk) -> English (canonical)
ES_TO_EN = {v: k for k, v in EN_TO_ES.items()}

# === LAYER MAPPING ===
LAYER_MAP = {
    FOLDER_INBOX: "L0",
    FOLDER_DECISIONS: "L3",
    FOLDER_KNOWLEDGE: "L3",
    FOLDER_EPISODES: "L2",
    FOLDER_ENTITIES: "L3",
    FOLDER_NOTES: "L3",
    FOLDER_PEOPLE: "L3",
    FOLDER_TEMPLATES: "L3",
}

# === TYPE CODES (for filename generation) ===
TYPE_CODES = {
    FOLDER_INBOX: "INBOX",
    FOLDER_DECISIONS: "DECISION",
    FOLDER_KNOWLEDGE: "KNOWLEDGE",
    FOLDER_EPISODES: "EPISODE",
    FOLDER_ENTITIES: "ENTITY",
    FOLDER_NOTES: "NOTE",
    FOLDER_PEOPLE: "PERSON",
    FOLDER_TEMPLATES: "TEMPLATE",
}

# === TAG TO FOLDER (for Obsidian classification) ===
TAG_TO_FOLDER = {
    "#decision": FOLDER_DECISIONS,
    "#conocimiento": FOLDER_KNOWLEDGE,
    "#episodio": FOLDER_EPISODES,
    "#entidad": FOLDER_ENTITIES,
    "#nota": FOLDER_NOTES,
    "#persona": FOLDER_PEOPLE,
}

# === HELPER FUNCTIONS ===
def to_disk_folder(en_folder: str) -> str:
    """Convert canonical English folder name to user-facing Spanish disk name."""
    return EN_TO_ES.get(en_folder, en_folder)

def to_canonical(disk_folder: str) -> str:
    """Convert user-facing Spanish disk name to canonical English name."""
    return ES_TO_EN.get(disk_folder, disk_folder.lower())

def get_all_disk_folders() -> list:
    """Get all Spanish disk folder names."""
    return list(EN_TO_ES.values())

def get_all_en_folders() -> list:
    """Get all canonical English folder names."""
    return list(ALL_FOLDERS)

def get_layer(en_folder: str) -> str:
    """Get memory layer for a folder."""
    return LAYER_MAP.get(en_folder, "L3")

def get_type_code(en_folder: str) -> str:
    """Get type code for filename generation."""
    return TYPE_CODES.get(en_folder, "NOTE")

def classify_tag_to_folder(tag: str) -> str:
    """Map a tag to canonical folder name."""
    return TAG_TO_FOLDER.get(tag.lower(), FOLDER_NOTES)
