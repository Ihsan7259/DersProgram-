"""Birden fazla kurumu (şube/okul) aynı programdan yönetme desteği.

Her kurum kendi ayrı SQLite dosyasında saklanır (bkz. db.Database). Bu
modül sadece "hangi kurumlar var, dosyaları nerede, hangisi şu an aktif"
bilgisini basit JSON dosyalarında tutar - veritabanı şemasıyla hiçbir
ilgisi yoktur.

ÖNEMLİ: Uygulamanın önceki (tek kurumlu) sürümlerinden kalan `veri.db`
dosyası hiçbir zaman silinmez ya da yeniden adlandırılmaz; ilk kez bu
özellik devreye girdiğinde sadece "Ana Kurum" adıyla kayda eklenir, yeni
kurumlar bunun YANINA (ayrı dosyalar olarak) eklenir.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .db import default_db_path

REGISTRY_FILENAME = "kurumlar.json"
ACTIVE_MARKER_FILENAME = "aktif_kurum.json"
DEFAULT_INSTITUTION_NAME = "Ana Kurum"


def data_dir() -> Path:
    d = default_db_path().parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def _registry_path() -> Path:
    return data_dir() / REGISTRY_FILENAME


def _active_marker_path() -> Path:
    return data_dir() / ACTIVE_MARKER_FILENAME


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return slug or "kurum"


def _load_registry() -> list[dict]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_registry(entries: list[dict]) -> None:
    with open(_registry_path(), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def list_institutions() -> list[dict]:
    """[{"name": str, "file": str}, ...] döner.

    Kayıt hiç yoksa ve daha önceki (tek kurumlu) sürümden kalan `veri.db`
    diskte varsa, o dosya silinip taşınmadan sadece "Ana Kurum" adıyla
    kayda eklenir.
    """
    entries = _load_registry()
    if entries:
        return entries
    default_path = default_db_path()
    if default_path.exists():
        entries = [{"name": DEFAULT_INSTITUTION_NAME, "file": default_path.name}]
        _save_registry(entries)
    return entries


def _ensure_default_entry() -> dict:
    entries = list_institutions()
    if entries:
        return entries[0]
    entry = {"name": DEFAULT_INSTITUTION_NAME, "file": default_db_path().name}
    _save_registry([entry])
    return entry


def add_institution(display_name: str) -> dict:
    """Yeni bir kurum tanımı ekler (henüz dosyasını OLUŞTURMAZ - dosya,
    o kuruma ilk kez geçildiğinde db.Database tarafından oluşturulur)."""
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Kurum adı boş olamaz.")
    entries = list_institutions()
    if not entries:
        entries = [_ensure_default_entry()]
    if any(e["name"].strip().lower() == display_name.lower() for e in entries):
        raise ValueError(f"'{display_name}' adında bir kurum zaten var.")

    existing_files = {e["file"] for e in entries}
    base_slug = _slugify(display_name)
    filename = f"{base_slug}.db"
    counter = 2
    while filename in existing_files or (data_dir() / filename).exists():
        filename = f"{base_slug}_{counter}.db"
        counter += 1

    entry = {"name": display_name, "file": filename}
    entries.append(entry)
    _save_registry(entries)
    return entry


def get_active_institution() -> dict:
    entries = list_institutions()
    if not entries:
        entries = [_ensure_default_entry()]
    marker = _active_marker_path()
    active_file = None
    if marker.exists():
        try:
            with open(marker, "r", encoding="utf-8") as f:
                active_file = json.load(f).get("file")
        except (json.JSONDecodeError, OSError):
            active_file = None
    for entry in entries:
        if entry["file"] == active_file:
            return entry
    return entries[0]


def set_active_institution(entry: dict) -> None:
    with open(_active_marker_path(), "w", encoding="utf-8") as f:
        json.dump({"file": entry["file"]}, f, ensure_ascii=False)


def institution_db_path(entry: dict) -> Path:
    return data_dir() / entry["file"]
