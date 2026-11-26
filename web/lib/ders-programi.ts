// Ders Programı masaüstü uygulamasının "Siteye Yayınla" ile gizli GitHub
// deposuna yüklediği kişisel program dosyalarını okur.
//
// Her link için bir dosya var: <klasör>/<kod>.json (bkz. README.md).
// Bu modül sadece sunucu tarafında kullanılmalı: GitHub token'ı tarayıcıya
// asla gitmemeli.
import { readFile } from "node:fs/promises";
import path from "node:path";

// Izgaranın bir hücresi, uygulamadaki önizlemenin ("Kopyala" görseli)
// çizdiği haliyle. Hücrede ya kartlar, ya (4+ derslik kalabalık hücrede)
// tek satırlık adlar, ya öğretmenin "müsait değil" işareti, ya da resmî
// tatil olan günlerde tatilin adı olur.
export type ScheduleCell = {
  day: number; // 0 = haftanın ilk günü (days[0], genelde Pazartesi)
  period: number; // 1'den başlar (periods[period - 1])
  cards?: { lines: string[]; color: string }[]; // lines: [kalın satır, ikinci, küçük üçüncü]
  names?: string[];
  color?: string; // names için arka plan
  unavailable?: boolean;
  holiday?: string; // resmî tatil: o günün bütün saatleri, tatilin adıyla
};

export type ProgramWeek = {
  label: string; // "23 Kas 2026 – 27 Kas 2026"
  cells: ScheduleCell[];
};

export type ProgramPage = {
  format: number;
  institution: string;
  kind: "teacher" | "student" | "class";
  kindLabel: string;
  name: string;
  subtitle: string;
  days: string[];
  periods: { no: number; start: string; end: string }[];
  // Haftanın pazartesisi (YYYY-AA-GG) -> o hafta
  weeks: Record<string, ProgramWeek>;
  publishedAt: string;
};

// Uygulamanın ürettiği kodlar: küçük harf + rakam. Başka bir şey kabul
// etmemek, dosya yolu oyunlarının (../ gibi) da önünü keser.
const CODE_PATTERN = /^[a-z0-9]{6,32}$/;

// Sayfanın en fazla ne kadar eski veriyi göstereceği (saniye). Uygulamada
// "Siteye Yayınla"ya basıldıktan en geç bu kadar sonra linkler güncellenir.
const REVALIDATE_SECONDS = 60;

export async function getProgramPage(code: string): Promise<ProgramPage | null> {
  if (!CODE_PATTERN.test(code)) return null;

  // Yerel deneme için: GitHub yerine bir klasörden oku.
  const localDir = process.env.DERS_PROGRAMI_LOCAL_DIR;
  if (localDir) {
    try {
      const text = await readFile(path.join(localDir, `${code}.json`), "utf8");
      return JSON.parse(text) as ProgramPage;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  const repo = process.env.DERS_PROGRAMI_REPO;
  const token = process.env.DERS_PROGRAMI_TOKEN;
  const branch = process.env.DERS_PROGRAMI_BRANCH || "main";
  const folder = (process.env.DERS_PROGRAMI_FOLDER ?? "programlar").replace(/^\/+|\/+$/g, "");
  if (!repo || !token) {
    throw new Error("DERS_PROGRAMI_REPO ve DERS_PROGRAMI_TOKEN ortam değişkenleri tanımlı değil.");
  }

  const filePath = folder ? `${folder}/${code}.json` : `${code}.json`;
  const response = await fetch(
    `https://api.github.com/repos/${repo}/contents/${filePath}?ref=${encodeURIComponent(branch)}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      next: { revalidate: REVALIDATE_SECONDS },
    },
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Ders programı okunamadı: GitHub ${response.status}`);
  }
  return (await response.json()) as ProgramPage;
}

// Türkiye saatine göre bugünün tarihi ve içinde bulunulan haftanın
// pazartesisi. Sayfa hep "bu haftayı" gösterir; pazartesi yeni haftaya geçer.
export function currentWeek(now: Date = new Date()): { today: string; monday: string } {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Istanbul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const date = new Date(`${today}T00:00:00Z`);
  const daysSinceMonday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - daysSinceMonday);
  return { today, monday: date.toISOString().slice(0, 10) };
}

// İndirilen görselin dosya adı: "Zeynep_Yildiz_23_Kas_2026.png". Türkçe
// harfler sadeleştirilir: bazı tarayıcılar (ör. Chromium) Türkçe karakterli
// dosya adlarını reddedip dosyayı "download" adıyla kaydediyor.
const TURKISH_ASCII: Record<string, string> = {
  ç: "c", Ç: "C", ğ: "g", Ğ: "G", ı: "i", İ: "I", ö: "o", Ö: "O", ş: "s", Ş: "S", ü: "u", Ü: "U",
};

export function downloadFilename(page: ProgramPage, week: ProgramWeek): string {
  const firstDay = week.label.split("–")[0] ?? "";
  const text = `${page.name} ${firstDay}`
    .replace(/[çÇğĞıİöÖşŞüÜ]/g, (letter) => TURKISH_ASCII[letter])
    .normalize("NFKD")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `${text || "ders_programi"}.png`;
}

// Yayın zamanı uygulamanın çalıştığı bilgisayarın yerel saatiyle yazılır
// (saat dilimi bilgisi olmadan); olduğu gibi gösterilir.
export function formatPublishedAt(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) return value;
  const [, year, month, day, hour, minute] = match;
  return `${day}.${month}.${year} ${hour}:${minute}`;
}
