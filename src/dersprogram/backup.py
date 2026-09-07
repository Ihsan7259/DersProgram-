"""Sessiz otomatik yedekleme.

Kullanıcı hiçbir şey görmeden/yapmadan: program çalışırken belirli
aralıklarla, kurum değiştirilirken ve program kapanırken veritabanının
tutarlı bir kopyası ayrı bir "Yedekler" klasörüne alınır. Birden fazla
bilgisayarda çalışan kurumlar için Ayarlar sekmesindeki "Yedeği Dışa
Aktar"/"Yedekten Geri Yükle" düğmeleriyle bu dosyalar elle de taşınabilir
(bkz. ui/settings_tab.py)."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .db import Database, default_db_path

BACKUPS_DIRNAME = "Yedekler"
# Kurum başına saklanan otomatik yedek sayısı - sınırsız birikip diski
# doldurmasın diye eskiler sessizce silinir (elle "Dışa Aktar" ile alınan
# yedekler bu klasörün dışında olduğu için bundan etkilenmez).
MAX_BACKUPS_PER_INSTITUTION = 20


def backups_dir() -> Path:
    d = default_db_path().parent / BACKUPS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup_now(db: Database, institution_file: str) -> Path | None:
    """db'yi Yedekler klasörüne zaman damgalı bir kopya olarak yazar.
    Sessizce çalışır - disk dolu gibi bir hata olursa kullanıcının işini
    kesintiye uğratmamak için yutulur (yedekleme başarısız olsa da program
    normal şekilde kullanılmaya devam edebilmeli)."""
    stem = Path(institution_file).stem
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups_dir() / f"{stem}_{timestamp}.db"
    try:
        db.backup_to(dest)
    except Exception:
        return None
    _cleanup_old_backups(stem)
    return dest


def _cleanup_old_backups(stem: str) -> None:
    try:
        matches = sorted(backups_dir().glob(f"{stem}_*.db"), key=lambda p: p.name)
        excess = len(matches) - MAX_BACKUPS_PER_INSTITUTION
        for path in matches[:max(0, excess)]:
            path.unlink(missing_ok=True)
    except OSError:
        pass
