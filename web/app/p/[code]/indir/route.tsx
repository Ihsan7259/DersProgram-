// /p/<kod>/indir: sayfada görünen haftanın programını, uygulamadaki
// "Kopyala" görselinin aynısı olarak PNG dosyası olarak indirir.
import { currentWeek, downloadFilename, getProgramPage } from "../../../../lib/ders-programi";
import { programImage } from "../../../../lib/ders-programi-gorsel";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const page = await getProgramPage(code);
  if (!page) {
    return new Response("Link geçersiz.", { status: 404, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  const { monday } = currentWeek();
  const week = page.weeks[monday];
  if (!week) {
    return new Response("Bu haftanın programı henüz yayınlanmadı.", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return programImage(page, week, downloadFilename(page, week));
}
