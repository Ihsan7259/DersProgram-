// Kişisel ders programı sayfası: /p/<kod>
//
// Link, Ders Programı uygulamasının "Linkler" sayfasından bir kere
// gönderilir. Sayfa her açılışta Türkiye saatine göre o haftanın programını
// gösterir (pazartesi yeni haftaya geçer); içerik uygulamada "Siteye
// Yayınla"ya basıldıkça güncellenir.
//
// Görünüm, uygulamadan alınan program görselinin ("Kopyala") aynısıdır:
// satırlar günler, sütunlar ders saatleri. Izgara bir resim gibi ekrana
// sığacak şekilde orantılı küçülür; telefonda iki parmakla yakınlaştırılır.
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import localFont from "next/font/local";
import {
  currentWeek,
  downloadFilename,
  formatPublishedAt,
  getProgramPage,
  type ProgramPage,
  type ScheduleCell,
} from "../../../lib/ders-programi";
import styles from "./program.module.css";

// Uygulamanın kendi yazı tipi (indirilen görsel de aynısını kullanır).
const workSans = localFont({
  src: [
    { path: "./fonts/WorkSans-Regular.ttf", weight: "400", style: "normal" },
    { path: "./fonts/WorkSans-Bold.ttf", weight: "700", style: "normal" },
  ],
  display: "swap",
});

// Hafta, isteğin yapıldığı güne göre seçildiği için sayfa her istekte
// yeniden çizilir; GitHub'dan okunan veri ise ayrıca önbellekte tutulur
// (bkz. lib/ders-programi.ts, REVALIDATE_SECONDS).
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ code: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { code } = await params;
  const page = await getProgramPage(code);
  return {
    title: page ? `${page.name} - Ders Programı` : "Ders Programı",
    // Kişisel sayfalar arama motorlarında asla görünmemeli.
    robots: { index: false, follow: false },
  };
}

export default async function ProgramPageView({ params }: Props) {
  const { code } = await params;
  const page = await getProgramPage(code);
  if (!page) {
    return (
      <main className={`${styles.page} ${workSans.className}`}>
        <h1 className={styles.title}>Link geçersiz</h1>
        <p className={styles.subtitle}>
          Bu link geçerli değil ya da yenilenmiş olabilir. Güncel linkinizi kurumdan isteyin.
        </p>
      </main>
    );
  }

  const { monday } = currentWeek();
  const week = page.weeks[monday];

  return (
    <main className={`${styles.page} ${workSans.className}`}>
      <div className={styles.heading}>
        <div>
          <h1 className={styles.title}>{page.name}</h1>
          <p className={styles.subtitle}>{week ? week.label : "Bu haftanın programı henüz yayınlanmadı."}</p>
        </div>
        {week && (
          // Göreli adres: /p/<kod> -> /p/<kod>/indir (sitede /p dışında bir
          // yola taşınsa da çalışır).
          <a className={styles.download} href={`${code}/indir`} download={downloadFilename(page, week)}>
            Resim olarak indir
          </a>
        )}
      </div>
      {week && <Grid page={page} cells={week.cells} />}
      <p className={styles.footer}>
        {page.institution} · Son güncelleme: {formatPublishedAt(page.publishedAt)}
      </p>
    </main>
  );
}

function Grid({ page, cells }: { page: ProgramPage; cells: ScheduleCell[] }) {
  const byPosition = new Map(cells.map((cell) => [`${cell.day}-${cell.period}`, cell]));
  const sheetStyle = { "--cols": page.periods.length } as CSSProperties;
  return (
    <div className={styles.frame}>
      <div className={styles.sheet} style={sheetStyle}>
        <div className={styles.corner} />
        {page.periods.map((period) => (
          <div key={period.no} className={styles.periodHeader}>
            {period.no}.
            {period.start && (
              <>
                <br />
                {period.start}-
                <br />
                {period.end}
              </>
            )}
          </div>
        ))}
        {page.days.map((dayName, day) => (
          <Row key={dayName} dayName={dayName} day={day} page={page} byPosition={byPosition} />
        ))}
      </div>
    </div>
  );
}

function Row({
  dayName,
  day,
  page,
  byPosition,
}: {
  dayName: string;
  day: number;
  page: ProgramPage;
  byPosition: Map<string, ScheduleCell>;
}) {
  return (
    <>
      <div className={styles.dayHeader}>{dayName}</div>
      {page.periods.map((period) => (
        <Cell key={period.no} cell={byPosition.get(`${day}-${period.no}`)} />
      ))}
    </>
  );
}

function Cell({ cell }: { cell?: ScheduleCell }) {
  if (cell?.cards?.length) {
    return (
      <div className={styles.cell}>
        {cell.cards.map((card, index) => (
          <div key={index} className={styles.card} style={{ background: card.color }}>
            <span className={styles.primary}>{card.lines[0]}</span>
            {card.lines[1] && <span className={styles.secondary}>{card.lines[1]}</span>}
            {card.lines[2] && <span className={styles.tertiary}>{card.lines[2]}</span>}
          </div>
        ))}
      </div>
    );
  }
  if (cell?.names?.length) {
    const count = cell.names.length;
    const [columns, fontPx] = count <= 5 ? [1, 15] : count <= 10 ? [2, 12.3] : [3, 10.2];
    const namesStyle = { background: cell.color, "--name-cols": columns, "--name-px": fontPx } as CSSProperties;
    return (
      <div className={styles.cell}>
        <div className={styles.names} style={namesStyle}>
          {cell.names.map((name, index) => (
            <span key={index} className={styles.name} title={name}>
              {name}
            </span>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className={styles.cell}>
      <div className={styles.empty}>
        {cell?.unavailable && (
          <span className={styles.unavailable} title="Bu saatte müsait değil">
            ×
          </span>
        )}
      </div>
    </div>
  );
}
