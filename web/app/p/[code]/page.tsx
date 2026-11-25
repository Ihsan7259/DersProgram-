// Kişisel ders programı sayfası: /p/<kod>
//
// Link, Ders Programı uygulamasının "Linkler" sayfasından bir kere
// gönderilir. Sayfa her açılışta Türkiye saatine göre o haftanın programını
// gösterir (pazartesi yeni haftaya geçer); içerik uygulamada "Siteye
// Yayınla"ya basıldıkça güncellenir.
import type { Metadata } from "next";
import {
  addDays,
  currentWeek,
  formatDate,
  formatPublishedAt,
  getProgramPage,
  type LessonEntry,
  type ProgramPage,
} from "../../../lib/ders-programi";
import styles from "./program.module.css";

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
      <main className={styles.page}>
        <div className={styles.notice}>
          <h1>Link geçersiz</h1>
          <p>Bu link geçerli değil ya da yenilenmiş olabilir. Güncel linkinizi kurumdan isteyin.</p>
        </div>
      </main>
    );
  }

  const { today, monday } = currentWeek();
  const lessons = page.weeks[monday];
  const lastDay = addDays(monday, Math.max(page.days.length, 1) - 1);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <p className={styles.institution}>{page.institution}</p>
        <h1 className={styles.name}>{page.name}</h1>
        <p className={styles.meta}>
          {page.kindLabel}
          {page.subtitle ? ` · ${page.subtitle}` : ""}
        </p>
        <p className={styles.week}>
          {formatDate(monday, { day: "numeric", month: "long" })} –{" "}
          {formatDate(lastDay, { day: "numeric", month: "long", year: "numeric" })}
        </p>
      </header>

      {lessons === undefined ? (
        <div className={styles.notice}>
          <p>Bu haftanın programı henüz yayınlanmadı.</p>
        </div>
      ) : (
        page.days.map((dayName, dayIndex) => (
          <DaySection
            key={dayName}
            page={page}
            dayName={dayName}
            date={addDays(monday, dayIndex)}
            isToday={addDays(monday, dayIndex) === today}
            lessons={lessons.filter((lesson) => lesson.day === dayIndex)}
          />
        ))
      )}

      <footer className={styles.footer}>Son güncelleme: {formatPublishedAt(page.publishedAt)}</footer>
    </main>
  );
}

function DaySection({
  page,
  dayName,
  date,
  isToday,
  lessons,
}: {
  page: ProgramPage;
  dayName: string;
  date: string;
  isToday: boolean;
  lessons: LessonEntry[];
}) {
  return (
    <section className={isToday ? `${styles.day} ${styles.today}` : styles.day}>
      <h2 className={styles.dayTitle}>
        <span>{dayName}</span>
        <span className={styles.dayDate}>{formatDate(date, { day: "numeric", month: "long" })}</span>
        {isToday && <span className={styles.todayBadge}>Bugün</span>}
      </h2>
      {lessons.length === 0 ? (
        <p className={styles.empty}>Ders yok</p>
      ) : (
        <ul className={styles.lessons}>
          {lessons.map((lesson, index) => (
            <LessonRow key={`${lesson.period}-${index}`} page={page} lesson={lesson} />
          ))}
        </ul>
      )}
    </section>
  );
}

function LessonRow({ page, lesson }: { page: ProgramPage; lesson: LessonEntry }) {
  const period = page.periods[lesson.period - 1];
  // "Zümre" gibi türlerde başlık zaten türün adı; etiketi tekrar yazma.
  const showType = lesson.typeLabel !== lesson.title;
  return (
    <li className={styles.lesson}>
      <div className={styles.time}>
        <span className={styles.periodNo}>{lesson.period}. ders</span>
        {period?.start && (
          <span>
            {period.start}
            {period.end ? `–${period.end}` : ""}
          </span>
        )}
      </div>
      <div className={styles.card} style={{ background: lesson.color, borderLeftColor: lesson.accent }}>
        <p className={styles.title}>{lesson.title}</p>
        {lesson.subtitle && <p className={styles.subtitle}>{lesson.subtitle}</p>}
        {(showType || lesson.room) && (
          <p className={styles.tags}>
            {showType && (
              <span className={styles.tag} style={{ color: lesson.accent }}>
                {lesson.typeLabel}
              </span>
            )}
            {lesson.room && <span className={styles.tag}>{lesson.room}</span>}
          </p>
        )}
      </div>
    </li>
  );
}
