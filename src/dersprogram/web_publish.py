"""Kişisel web linkleri ve "Siteye Yayınla".

Kullanıcı isteği: ekran görüntülerini WhatsApp'tan tek tek atınca hesap
spam diye kısıtlanıyordu. Artık her öğretmen, öğrenci ve sınıfın
rastgele kodlu KALICI bir linki var (ör. https://vipparkkurs.com/p/k7q2mxp9wd).
Link bir kere gönderilir; program her yayınlandığında linkteki program
kendiliğinden güncellenir.

Yayın şöyle çalışır: her link için küçük bir JSON dosyası üretilir
(<klasör>/<kod>.json) ve hepsi TEK bir commit ile gizli (private) bir
GitHub deposuna yüklenir. Kurumun Next.js sitesi bu dosyaları sunucu
tarafında okuyup /p/<kod> sayfasında gösterir (bkz. web/README.md). Sitede
veritabanı ya da veri alan bir endpoint gerekmez.

Kodlar ayarlar tablosunda ("web_share_codes") tutulur; kurumun veritabanı
yedeklerine de girer, yani yedekten geri dönülse bile linkler değişmez.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import secrets
import urllib.error
import urllib.request

from .db import Database
from . import scheduling

KIND_TEACHER = "teacher"
KIND_STUDENT = "student"
KIND_CLASS = "class"
KIND_LABELS = {KIND_TEACHER: "Öğretmen", KIND_STUDENT: "Öğrenci", KIND_CLASS: "Sınıf"}

# Karışabilecek karakterler (0/o, 1/l/i) yok - link elle yazılırsa da
# hata çıkmasın. 31^10 ≈ 8 * 10^14 olasılık: deneme yanılmayla bulunamaz.
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LENGTH = 10

# Bu haftayla birlikte kaç hafta yayınlanır. Site bugünün tarihine göre
# o haftayı gösterir (pazartesi yeni hafta); birkaç hafta ileriyi de
# yüklemek, bir süre yayın yapılmasa bile linklerin boş kalmamasını sağlar.
PUBLISH_WEEKS = 4

PAYLOAD_FORMAT = 1

SETTING_CODES = "web_share_codes"
SETTING_CONFIG = "web_publish"
SETTING_LAST = "web_last_publish"

DEFAULT_CONFIG = {
    "base_url": "https://vipparkkurs.com/p/",
    "repo": "",
    "branch": "main",
    "folder": "programlar",
    "token": "",
}

GITHUB_API = "https://api.github.com"


class PublishError(Exception):
    """Kullanıcıya olduğu gibi gösterilebilecek (Türkçe) yayın hatası."""


# ---------- kodlar ve linkler ----------

def _new_code(existing: set[str]) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in existing:
            return code


def _codes(db: Database) -> dict[str, str]:
    return dict(db.get_setting(SETTING_CODES) or {})


def _entity_key(kind: str, entity_id: int) -> str:
    return f"{kind}:{entity_id}"


def _entities(db: Database) -> list[tuple[str, int, str, str]]:
    """(tür, id, ad, açıklama) - öğretmenler, sınıflar, öğrenciler; her
    biri kendi sekmesindeki sırayla."""
    items: list[tuple[str, int, str, str]] = []
    for row in db.list_teachers():
        items.append((KIND_TEACHER, row["id"], row["name"], row["subject_area"] or ""))
    for row in db.list_class_groups():
        items.append((KIND_CLASS, row["id"], row["name"], ""))
    for row in db.list_students():
        items.append((KIND_STUDENT, row["id"], row["name"], row["class_name"] or ""))
    return items


def ensure_codes(db: Database) -> dict[str, str]:
    """Kodu olmayan her öğretmen/sınıf/öğrenciye kod verir (bir kere
    verilen kod bir daha değişmez - sadece "Linki Yenile" değiştirir)."""
    codes = _codes(db)
    used = set(codes.values())
    changed = False
    for kind, entity_id, _name, _subtitle in _entities(db):
        key = _entity_key(kind, entity_id)
        if key not in codes:
            codes[key] = _new_code(used)
            used.add(codes[key])
            changed = True
    if changed:
        db.set_setting(SETTING_CODES, codes)
    return codes


def regenerate_code(db: Database, kind: str, entity_id: int) -> str:
    """Link başkasının eline geçtiyse: eski kod geçersiz olur (bir sonraki
    yayında eski dosya depodan silinir), yeni bir kod verilir."""
    codes = _codes(db)
    used = set(codes.values())
    code = _new_code(used)
    codes[_entity_key(kind, entity_id)] = code
    db.set_setting(SETTING_CODES, codes)
    return code


def get_config(db: Database) -> dict:
    config = dict(DEFAULT_CONFIG)
    config.update(db.get_setting(SETTING_CONFIG) or {})
    return config


def save_config(db: Database, config: dict) -> None:
    clean = {key: str(config.get(key, DEFAULT_CONFIG[key]) or "").strip() for key in DEFAULT_CONFIG}
    clean["folder"] = clean["folder"].strip("/")
    db.set_setting(SETTING_CONFIG, clean)


def is_configured(config: dict) -> bool:
    return bool(config.get("repo") and config.get("token") and config.get("branch"))


def link_for(config: dict, code: str) -> str:
    base = config.get("base_url") or DEFAULT_CONFIG["base_url"]
    if not base.endswith("/"):
        base += "/"
    return base + code


def list_links(db: Database) -> list[dict]:
    """Linkler sayfası ve Excel listesi için: her kişi/sınıf bir satır."""
    codes = ensure_codes(db)
    config = get_config(db)
    entries = []
    for kind, entity_id, name, subtitle in _entities(db):
        code = codes[_entity_key(kind, entity_id)]
        entries.append({
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "id": entity_id,
            "name": name,
            "subtitle": subtitle,
            "code": code,
            "url": link_for(config, code),
        })
    return entries


def whatsapp_message(entry: dict, institution: str) -> str:
    who = {
        KIND_TEACHER: "haftalık ders programınız",
        KIND_STUDENT: "haftalık ders programın",
        KIND_CLASS: f"{entry['name']} sınıfının haftalık ders programı",
    }[entry["kind"]]
    prefix = f"{institution} - " if institution else ""
    return (
        f"{prefix}{entry['name']}, {who} bu linkte:\n{entry['url']}\n\n"
        "Link hep aynı kalır, program değiştikçe kendiliğinden güncellenir. "
        "Kaydetmeniz yeterli."
    )


# ---------- yayınlanacak içerik ----------

def _entry_for(block: scheduling.BlockView, kind: str) -> dict:
    from .ui import theme

    if kind == KIND_TEACHER:
        title, subtitle, _room = block.teacher_row_lines()
    elif kind == KIND_CLASS:
        title = block.subject_name or block.type_label()
        subtitle = block.teacher_name or ""
    else:
        title = block.subject_name or block.type_short()
        subtitle = block.teacher_name or ""
    bg, dot = theme.lesson_colors_for(block)
    return {
        "day": block.day,
        "period": block.period,
        "title": title or block.type_label(),
        "subtitle": subtitle or "",
        "type": block.type,
        "typeLabel": block.type_short(),
        "room": block.room_name or "",
        "color": bg,
        "accent": dot,
    }


def _sorted_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: (e["day"], e["period"], e["title"]))


def build_pages(db: Database, institution: str, today: _dt.date | None = None) -> dict[str, dict]:
    """Kod -> o linkin JSON içeriği. Her dosya kendi başına yeterlidir
    (günler, ders saatleri, kurum adı içinde) ki site tek bir dosya
    okuyarak sayfayı çizebilsin."""
    today = today or _dt.date.today()
    first_week = scheduling.monday_of(today)
    weeks = [first_week + _dt.timedelta(weeks=i) for i in range(PUBLISH_WEEKS)]
    codes = ensure_codes(db)

    day_names = list(db.day_names)
    periods = []
    for number in range(1, db.period_count + 1):
        times = db.period_time_label(number)
        start, _, end = times.partition("-")
        periods.append({"no": number, "start": start, "end": end})

    students = [(row["id"], row["class_group_id"]) for row in db.list_students()]
    per_entity: dict[str, dict[str, list[dict]]] = {key: {} for key in codes}

    for week in weeks:
        wkey = scheduling.week_key(week)
        schedule, _pool = scheduling.get_week_view(db, week)
        buckets: dict[str, list[dict]] = {}
        for (day, period), blocks in schedule.items():
            for block in blocks:
                if block.teacher_id is not None:
                    buckets.setdefault(_entity_key(KIND_TEACHER, block.teacher_id), []).append(
                        _entry_for(block, KIND_TEACHER))
                if block.class_group_id is not None:
                    buckets.setdefault(_entity_key(KIND_CLASS, block.class_group_id), []).append(
                        _entry_for(block, KIND_CLASS))
            # Öğrencinin programı: kendi dersleri + sınıfının dersleri,
            # uygulamadaki Öğrenciler sekmesiyle birebir aynı kuralla.
            for student_id, class_group_id in students:
                for block in scheduling.student_cell_blocks(blocks, student_id, class_group_id):
                    buckets.setdefault(_entity_key(KIND_STUDENT, student_id), []).append(
                        _entry_for(block, KIND_STUDENT))
        for key in per_entity:
            per_entity[key][wkey] = _sorted_entries(buckets.get(key, []))

    pages: dict[str, dict] = {}
    for kind, entity_id, name, subtitle in _entities(db):
        key = _entity_key(kind, entity_id)
        pages[codes[key]] = {
            "format": PAYLOAD_FORMAT,
            "institution": institution,
            "kind": kind,
            "kindLabel": KIND_LABELS[kind],
            "name": name,
            "subtitle": subtitle,
            "days": day_names,
            "periods": periods,
            "weeks": per_entity.get(key, {}),
        }
    return pages


def pages_fingerprint(pages: dict[str, dict]) -> str:
    """İçerik değişti mi? (kapanışta "yayınlansın mı?" diye sormak için) -
    yayın zamanı damgası dışarıda tutulur."""
    text = json.dumps(pages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_unpublished_changes(db: Database, institution: str) -> bool:
    last = db.get_setting(SETTING_LAST) or {}
    return pages_fingerprint(build_pages(db, institution)) != last.get("fingerprint")


def last_publish_info(db: Database) -> dict:
    return dict(db.get_setting(SETTING_LAST) or {})


# ---------- GitHub'a yükleme ----------

class _GitHub:
    def __init__(self, repo: str, token: str, api: str | None = None):
        self.repo = repo.strip().strip("/")
        self.token = token.strip()
        # api: testlerde sahte bir sunucu verilebilsin diye.
        self.api = (api or GITHUB_API).rstrip("/")

    def request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"{self.api}/repos/{self.repo}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "DersProgrami",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = None
            return exc.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PublishError(
                "GitHub'a bağlanılamadı. İnternet bağlantınızı kontrol edin.\n\n"
                f"Ayrıntı: {exc}"
            ) from exc


def _explain(status: int, payload, action: str) -> PublishError:
    message = (payload or {}).get("message", "") if isinstance(payload, dict) else ""
    if status == 401:
        hint = "Token geçersiz ya da süresi dolmuş. Yayın Ayarları'ndan yeni bir token girin."
    elif status in (403, 404):
        hint = ("Depo bulunamadı ya da token'ın bu depoya yazma izni yok. Depo adını "
                "(kullanici/depo) ve token'ın 'Contents: Read and write' iznini kontrol edin.")
    else:
        hint = "GitHub beklenmeyen bir cevap verdi."
    detail = f"\n\nAyrıntı ({status}): {message}" if message else f"\n\nAyrıntı: HTTP {status}"
    return PublishError(f"{action} başarısız. {hint}{detail}")


def _initialize_empty_repo(gh: _GitHub, branch: str) -> None:
    """Hiç commit'i olmayan yepyeni bir depoda git API'si çalışmaz; tek
    bir README yükleyip dalı oluşturuyoruz."""
    content = base64.b64encode(
        "Ders Programı uygulamasının web yayını için veri deposu.\n".encode("utf-8")
    ).decode("ascii")
    status, payload = gh.request("PUT", "/contents/README.md", {
        "message": "Veri deposu olusturuldu", "content": content, "branch": branch,
    })
    if status not in (200, 201):
        raise _explain(status, payload, "Depoyu hazırlamak")


def test_connection(config: dict, api: str | None = None) -> str:
    """Ayarlar penceresindeki "Bağlantıyı Test Et": depoya erişilebiliyor
    ve yazılabiliyor mu? Başarılıysa kısa bir açıklama döner."""
    if not is_configured(config):
        raise PublishError("Depo adı, dal ve token alanlarının hepsi dolu olmalı.")
    gh = _GitHub(config["repo"], config["token"], api)
    status, payload = gh.request("GET", "")
    if status != 200:
        raise _explain(status, payload, "Depoya erişmek")
    permissions = (payload or {}).get("permissions") or {}
    if permissions and not permissions.get("push"):
        raise PublishError("Token depoyu okuyabiliyor ama YAZAMIYOR. Token'a 'Contents: Read and write' izni verin.")
    private = (payload or {}).get("private")
    note = "" if private else (
        "\n\nDİKKAT: Bu depo HERKESE AÇIK (public). Öğrenci adları ve programlar "
        "herkes tarafından görülebilir - depoyu GitHub'dan 'Private' yapın."
    )
    return f"Bağlantı başarılı: {config['repo']}{note}"


def publish(db: Database, institution: str, *, api: str | None = None,
            now: _dt.datetime | None = None) -> dict:
    """Bütün linkleri tek bir commit ile depoya yükler. Bu kurumun daha
    önce yüklediği ama artık geçersiz olan (yenilenen / silinen kişi)
    dosyalar aynı commit'te silinir; aynı klasörü kullanan BAŞKA bir
    kurumun dosyalarına dokunulmaz.

    Döner: {"published_at", "count", "removed", "changed"}"""
    config = get_config(db)
    if not is_configured(config):
        raise PublishError("Önce Yayın Ayarları'ndan GitHub deposunu ve token'ı girin.")
    now = now or _dt.datetime.now()
    pages = build_pages(db, institution, now.date())
    fingerprint = pages_fingerprint(pages)
    folder = config["folder"].strip("/")
    branch = config["branch"]
    prefix = f"{folder}/" if folder else ""

    gh = _GitHub(config["repo"], config["token"], api)
    status, ref = gh.request("GET", f"/git/ref/heads/{branch}")
    if status in (404, 409):
        _initialize_empty_repo(gh, branch)
        status, ref = gh.request("GET", f"/git/ref/heads/{branch}")
    if status != 200:
        raise _explain(status, ref, "Depodaki dalı okumak")
    parent_sha = ref["object"]["sha"]
    status, parent = gh.request("GET", f"/git/commits/{parent_sha}")
    if status != 200:
        raise _explain(status, parent, "Son commit'i okumak")

    published_at = now.replace(microsecond=0).isoformat()
    tree: list[dict] = []
    for code, page in pages.items():
        body = dict(page, publishedAt=published_at)
        tree.append({
            "path": f"{prefix}{code}.json",
            "mode": "100644",
            "type": "blob",
            "content": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        })

    last = last_publish_info(db)
    stale = [c for c in last.get("codes", []) if c not in pages]
    # Silinecek dosya depoda gerçekten var mı? Olmayan bir yolu silmeye
    # çalışmak GitHub'da hata verir.
    if stale:
        status, existing = gh.request("GET", f"/git/trees/{parent['tree']['sha']}?recursive=1")
        if status != 200:
            raise _explain(status, existing, "Depodaki dosyaları listelemek")
        existing_paths = {item["path"] for item in (existing or {}).get("tree", [])}
        for code in stale:
            path = f"{prefix}{code}.json"
            if path in existing_paths:
                tree.append({"path": path, "mode": "100644", "type": "blob", "sha": None})

    status, new_tree = gh.request("POST", "/git/trees", {"base_tree": parent["tree"]["sha"], "tree": tree})
    if status != 201:
        raise _explain(status, new_tree, "Dosyaları hazırlamak")

    changed = new_tree["sha"] != parent["tree"]["sha"]
    if changed:
        status, commit = gh.request("POST", "/git/commits", {
            "message": f"Program yayini {published_at} ({len(pages)} link)",
            "tree": new_tree["sha"],
            "parents": [parent_sha],
        })
        if status != 201:
            raise _explain(status, commit, "Yayını kaydetmek")
        status, payload = gh.request("PATCH", f"/git/refs/heads/{branch}", {"sha": commit["sha"]})
        if status != 200:
            raise _explain(status, payload, "Yayını göndermek")

    db.set_setting(SETTING_LAST, {
        "published_at": published_at,
        "fingerprint": fingerprint,
        "codes": sorted(pages),
    })
    return {"published_at": published_at, "count": len(pages), "removed": len(stale), "changed": changed}
