// "Resim olarak indir": haftalık programı, uygulamadaki "Kopyala"
// görselinin aynısı olarak PNG'ye çizer (sunucuda, next/og ile; ek paket
// gerekmez).
//
// Ölçüler uygulamanın dışa aktarımından alındı (ui/schedule_tab.py,
// _render_row_pixmap ve widgets.MiniScheduleGrid; 300 DPI): sütun 345 px,
// hücre 3:2, yazılar sütun genişliğine oranlı, kenar boşluğu 0.18 inç.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import type { ProgramPage, ProgramWeek, ScheduleCell } from "./ders-programi";

const COL = 345; // ders saati sütunu
const HEAD_COL = 135; // gün adları sütunu
const ROW_MIN = Math.round(COL / 1.5);
const PRIMARY = 34;
const SECONDARY = 28;
const TERTIARY = 23;
const HEADER = 26;
const MARGIN = 54;
const TITLE_H = 90;
const SUBTITLE_H = 60;
const GAP = 18;
const CARD_PAD_X = 7;
const CARD_PAD_Y = 5;

const INK = "#10161f";
const INK_MUTED = "#4b5768";
const HEADER_INK = "#434e5e";
const SUBTITLE_INK = "#737b86";
const HEADER_BG = "#f7f5f1";
const SURFACE = "#fcfcfa";
const BORDER = "#dee1e7";
const DASHED = "#d4d8dd";
const UNAVAILABLE = "#c92f36";

// Yazı tipleri sayfanın kendi klasöründe (app/p/[code]/fonts). Proje src/
// klasörü kullanıyorsa ikinci yol denenir; başka bir yere taşındıysa
// DERS_PROGRAMI_FONT_DIR ile verilebilir.
async function loadFonts() {
  const candidates = [
    process.env.DERS_PROGRAMI_FONT_DIR,
    path.join(process.cwd(), "app", "p", "[code]", "fonts"),
    path.join(process.cwd(), "src", "app", "p", "[code]", "fonts"),
  ].filter((dir): dir is string => Boolean(dir));
  for (const dir of candidates) {
    try {
      const [regular, bold] = await Promise.all([
        readFile(path.join(dir, "WorkSans-Regular.ttf")),
        readFile(path.join(dir, "WorkSans-Bold.ttf")),
      ]);
      return [
        { name: "Work Sans", data: regular, weight: 400 as const, style: "normal" as const },
        { name: "Work Sans", data: bold, weight: 700 as const, style: "normal" as const },
      ];
    } catch {
      // sıradaki yolu dene
    }
  }
  throw new Error("Program görseli için yazı tipleri bulunamadı (WorkSans-Regular.ttf / WorkSans-Bold.ttf).");
}

// Satır yükseklikleri resmin boyutu için önceden bilinmeli: uygulamada
// olduğu gibi satır en az 3:2 hücre yüksekliğinde, içerik sığmazsa uzar.
function textLines(text: string, fontPx: number, width: number): number {
  const perLine = Math.max(1, Math.floor(width / (fontPx * 0.56)));
  return Math.max(1, Math.ceil(text.length / perLine));
}

function nameLayout(count: number): { columns: number; fontPx: number } {
  if (count <= 5) return { columns: 1, fontPx: PRIMARY };
  if (count <= 10) return { columns: 2, fontPx: SECONDARY };
  return { columns: 3, fontPx: TERTIARY };
}

function cellHeight(cell: ScheduleCell | undefined): number {
  const inner = COL - 2 * CARD_PAD_X - 4;
  if (cell?.cards?.length) {
    const cards = cell.cards.map((card) => {
      const [primary = "", secondary = "", tertiary = ""] = card.lines;
      let height = 2 * CARD_PAD_Y + textLines(primary, PRIMARY, inner) * PRIMARY * 1.2;
      if (secondary) height += textLines(secondary, SECONDARY, inner) * SECONDARY * 1.2 + 1;
      if (tertiary) height += textLines(tertiary, TERTIARY, inner) * TERTIARY * 1.2 + 1;
      return height;
    });
    return cards.reduce((sum, h) => sum + h, 0) + (cards.length - 1) * 2 + 4;
  }
  if (cell?.names?.length) {
    const { columns, fontPx } = nameLayout(cell.names.length);
    return Math.ceil(cell.names.length / columns) * fontPx * 1.3 + 2 * CARD_PAD_Y + 4;
  }
  return 0;
}

function Cell({ cell, height }: { cell?: ScheduleCell; height: number }) {
  const box = {
    display: "flex",
    flexDirection: "column" as const,
    width: COL,
    height,
    padding: 2,
  };
  if (cell?.cards?.length) {
    return (
      <div style={{ ...box, gap: 2 }}>
        {cell.cards.map((card, index) => (
          <div
            key={index}
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              flexGrow: 1,
              padding: `${CARD_PAD_Y}px ${CARD_PAD_X}px`,
              background: card.color,
              gap: 1,
            }}
          >
            <div style={{ fontSize: PRIMARY, fontWeight: 700, color: INK, lineHeight: 1.2 }}>{card.lines[0]}</div>
            {card.lines[1] ? (
              <div style={{ fontSize: SECONDARY, color: INK_MUTED, lineHeight: 1.2 }}>{card.lines[1]}</div>
            ) : null}
            {card.lines[2] ? (
              <div style={{ fontSize: TERTIARY, color: INK_MUTED, lineHeight: 1.2 }}>{card.lines[2]}</div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }
  if (cell?.names?.length) {
    const { columns, fontPx } = nameLayout(cell.names.length);
    const width = Math.floor((COL - 4 - 2 * CARD_PAD_X - (columns - 1) * 8) / columns);
    return (
      <div style={box}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignContent: "center",
            flexGrow: 1,
            columnGap: 8,
            padding: `${CARD_PAD_Y}px ${CARD_PAD_X}px`,
            background: cell.color,
          }}
        >
          {cell.names.map((name, index) => (
            <div
              key={index}
              style={{
                width,
                fontSize: fontPx,
                fontWeight: 700,
                color: INK,
                lineHeight: 1.3,
                overflow: "hidden",
                whiteSpace: "nowrap",
                textOverflow: "ellipsis",
              }}
            >
              {name}
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div style={box}>
      <div
        style={{
          display: "flex",
          flexGrow: 1,
          alignItems: "center",
          justifyContent: "center",
          border: `3px dashed ${DASHED}`,
          color: UNAVAILABLE,
          fontSize: HEADER,
          fontWeight: 700,
        }}
      >
        {cell?.unavailable ? "×" : ""}
      </div>
    </div>
  );
}

export async function programImage(page: ProgramPage, week: ProgramWeek, filename: string): Promise<ImageResponse> {
  const byPosition = new Map(week.cells.map((cell) => [`${cell.day}-${cell.period}`, cell]));
  const hasTimes = page.periods.some((period) => period.start);
  const headerHeight = Math.ceil((hasTimes ? 3 : 1) * HEADER * 1.25) + 16;
  const rowHeights = page.days.map((_day, day) =>
    Math.ceil(
      Math.max(ROW_MIN, ...page.periods.map((period) => cellHeight(byPosition.get(`${day}-${period.no}`)))),
    ),
  );
  const gridWidth = HEAD_COL + page.periods.length * COL + 2;
  const gridHeight = headerHeight + 1 + rowHeights.reduce((sum, h) => sum + h, 0) + 2;
  const width = gridWidth + 2 * MARGIN;
  const height = MARGIN + TITLE_H + SUBTITLE_H + GAP + gridHeight + MARGIN;

  const headerCell = {
    display: "flex",
    background: HEADER_BG,
    color: HEADER_INK,
    fontSize: HEADER,
    fontWeight: 700,
    lineHeight: 1.25,
  };

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width,
          height,
          padding: MARGIN,
          background: "#ffffff",
          fontFamily: "Work Sans",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", height: TITLE_H, fontSize: 56, fontWeight: 700, color: INK }}>
          {page.name}
        </div>
        <div style={{ display: "flex", alignItems: "center", height: SUBTITLE_H, fontSize: 33, color: SUBTITLE_INK }}>
          {week.label}
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginTop: GAP,
            width: gridWidth,
            border: `1px solid ${BORDER}`,
            background: SURFACE,
          }}
        >
          <div style={{ display: "flex", height: headerHeight, borderBottom: `1px solid ${BORDER}` }}>
            <div style={{ ...headerCell, width: HEAD_COL }} />
            {page.periods.map((period) => (
              <div
                key={period.no}
                style={{
                  ...headerCell,
                  width: COL,
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <div>{`${period.no}.`}</div>
                {period.start ? <div>{`${period.start}-`}</div> : null}
                {period.start ? <div>{period.end}</div> : null}
              </div>
            ))}
          </div>
          {page.days.map((dayName, day) => (
            <div key={dayName} style={{ display: "flex", height: rowHeights[day] }}>
              <div style={{ ...headerCell, width: HEAD_COL, alignItems: "center", padding: "0 7px", fontWeight: 400 }}>
                {dayName}
              </div>
              {page.periods.map((period) => (
                <Cell key={period.no} cell={byPosition.get(`${day}-${period.no}`)} height={rowHeights[day]} />
              ))}
            </div>
          ))}
        </div>
      </div>
    ),
    {
      width,
      height,
      fonts: await loadFonts(),
      headers: {
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "private, no-store",
      },
    },
  );
}
