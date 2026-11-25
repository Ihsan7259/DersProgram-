# Kişisel ders programı linkleri: site tarafı (Next.js)

Ders Programı masaüstü uygulaması her öğretmen, öğrenci ve sınıf için rastgele kodlu kalıcı bir link üretir:

```
https://vipparkkurs.com/p/k7q2mxp9wd
```

Link kişiye bir kere gönderilir. Uygulamada **Linkler > Siteye Yayınla**'ya basıldıkça linkteki program güncellenir. Sayfa her açılışta Türkiye saatine göre **o haftayı** gösterir ve pazartesi yeni haftaya geçer.

Sitede veritabanı, giriş sistemi ya da veri alan bir endpoint **gerekmez**:

```
Masaüstü uygulama ──(Siteye Yayınla: tek commit)──> private GitHub deposu
                                                       programlar/<kod>.json
Next.js /p/[code] ──(sunucu tarafında, 60 sn cache)──> aynı depo (read-only token)
```

## Kurulum

### 1. Veri deposu
GitHub'da **private** bir depo açın (ör. `vipparkkurs-program-veri`). "Add a README file" işaretli olabilir; boş da olabilir, uygulama ilk yayında hazırlar.

> Depo **private** olmalı: içinde öğrenci adları ve programlar var. Uygulamadaki "Bağlantıyı Test Et" depo public ise uyarır.

### 2. İki token (GitHub > Settings > Developer settings > Fine-grained tokens)
| Token | Nerede kullanılır | Repository access | İzin |
|---|---|---|---|
| Yazma | Masaüstü uygulama | Sadece veri deposu | Contents: **Read and write** |
| Okuma | Next.js sitesi | Sadece veri deposu | Contents: **Read-only** |

Token'ların bir son kullanma tarihi var. Süresi dolunca yenisini girmek gerekir; uygulama bu durumda "Token geçersiz" diye uyarır.

### 3. Dosyaları projeye ekleyin
```
lib/ders-programi.ts            ->  <proje>/lib/ders-programi.ts      (src/ kullanılıyorsa src/lib/)
app/p/[code]/page.tsx           ->  <proje>/app/p/[code]/page.tsx     (src/ kullanılıyorsa src/app/)
app/p/[code]/program.module.css ->  <proje>/app/p/[code]/program.module.css
```
`page.tsx` lib'i göreli yolla (`../../../lib/ders-programi`) içe aktarır. Projede `@/lib/...` alias'ı varsa onu kullanabilirsiniz. Ek bir npm paketi gerekmez.

### 4. Ortam değişkenleri (`.env.local` / Vercel > Environment Variables)
```
DERS_PROGRAMI_REPO=kullanici/vipparkkurs-program-veri
DERS_PROGRAMI_TOKEN=github_pat_...        # okuma token'ı
DERS_PROGRAMI_BRANCH=main                 # varsayılan: main
DERS_PROGRAMI_FOLDER=programlar           # varsayılan: programlar
```

### 5. Uygulamada ayar
**Linkler > Yayın Ayarları**: Link adresi `https://vipparkkurs.com/p/`, GitHub deposu `kullanici/vipparkkurs-program-veri`, yazma token'ı. Sonra **Bağlantıyı Test Et** ve **Siteye Yayınla**.

## Yerelde deneme
GitHub olmadan, bir klasördeki JSON dosyalarıyla:
```
DERS_PROGRAMI_LOCAL_DIR=/yol/programlar npm run dev
# http://localhost:3000/p/<kod>
```
Örnek bir dosya: [`ornek-veri/ornekkod01.json`](ornek-veri/ornekkod01.json). `DERS_PROGRAMI_LOCAL_DIR=web/ornek-veri` ile `http://localhost:3000/p/ornekkod01` açılır.
Örnek dosyada 23 Kasım - 14 Aralık 2026 haftaları var; başka bir tarihte "henüz yayınlanmadı" görünür. Denemek için `weeks` içindeki bir anahtarı o haftanın pazartesisiyle değiştirin.

## Notlar
- **Next.js sürümü:** App Router içindir. Next.js 16.4 ile derlenip test edildi (Next 15+ uyumlu). Next 14'te `params` bir Promise değildir; `Props` tipini `{ params: { code: string } }` yapıp `await params` satırlarını `params` ile değiştirin. Pages Router kullanılıyorsa aynı mantık `getServerSideProps` ile kurulabilir.
- **`cacheComponents`:** `next.config`'de açıksa `export const dynamic = "force-dynamic"` satırı kaldırılmalı.
- **Middleware:** Sitede bütün sayfalara giriş isteyen bir middleware varsa `/p/` yolu hariç tutulmalı; linkler girişsiz açılır.
- **Geçersiz kod:** "Link geçersiz" mesajı gösterilir. Kod formatına uymayan istekler (ör. `../`) GitHub'a hiç gitmez.
- **Arama motorları:** Sayfalar `noindex, nofollow` döner.
- **Cache:** Her kodun dosyası en fazla 60 saniyede bir GitHub'dan okunur (`REVALIDATE_SECONDS`). Token başına saatlik 5.000 istek sınırına uzak kalır.
- **Linki yenileme:** Uygulamada "Linki Yenile" denirse bir sonraki yayında eski kodun dosyası depodan silinir ve eski link "Link geçersiz" gösterir.

## Veri formatı (`programlar/<kod>.json`)
```jsonc
{
  "format": 1,
  "institution": "VIP Park Kurs",
  "kind": "student",              // teacher | student | class
  "kindLabel": "Öğrenci",
  "name": "Zeynep Yıldız",
  "subtitle": "9-A",              // öğrencide sınıfı, öğretmende branşları
  "days": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"],
  "periods": [{ "no": 1, "start": "08:00", "end": "08:40" }],
  "weeks": {                      // haftanın pazartesisi -> dersler (bu hafta + 3 hafta ileri)
    "2026-11-23": [
      {
        "day": 0,                 // days[0]
        "period": 1,              // periods[0]
        "title": "Matematik",
        "subtitle": "Ahmet Yılmaz",
        "type": "sinif",
        "typeLabel": "Sınıf",
        "room": "Derslik 101",
        "color": "#f8ddd0",       // uygulamadaki ders rengi
        "accent": "#b24a16"
      }
    ]
  },
  "publishedAt": "2026-11-25T14:30:05"
}
```
