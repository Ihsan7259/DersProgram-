# Ders Programı

Bir eğitim kurumunun (sınıf dersleri + birebir dersler + koçluk + zümre +
soru çözümü) haftalık ders programını hazırlamak için masaüstü uygulaması.
Windows için, tek kullanıcılı, internete ihtiyaç duymadan (offline) çalışır.

## Özellikler (v2)

- **Tanımlar**: Öğretmen (branş bilgisiyle), Öğrenci (sınıf + koç ataması,
  ücret bilgisi), Sınıf, Ders/Branş, Derslik
- **Ders tipleri**: Sınıf Dersi, Birebir Ders, Öğrenci Koçluk (koç
  atanınca otomatik oluşur), Zümre, Soru Çözümü
- **Ana Program**: kurum genelinde tek büyük haftalık ızgara.
  - "Ders Ekle" ile (ör. "9-A sınıfına haftada 4 saat Matematik") N adet
    1 saatlik ders bloğu **Atanmamış Dersler** havuzuna düşer
  - Havuzdan bir dersi sürükleyip ızgaraya bırakabilirsiniz; sürüklerken
    uygun hücreler yeşil, çakışan hücreler kırmızı görünür
  - Bir dersi yerleştirirken/kaldırırken **sadece bu hafta mı yoksa her
    hafta (kalıcı) mı** olacağı sorulur — şablon + istisna mantığı
  - **Oto Ata**: kalan atanmamış dersleri, günlere dengeli dağıtarak ve
    aynı gruptan art arda en fazla 2 saat gelecek şekilde otomatik yerleştirir
  - Sağ/sol oklarla haftalar arasında gezinilir
- **Öğretmenler / Öğrenciler / Sınıflar** sekmelerinde seçilen kişinin/sınıfın
  o haftaki filtrelenmiş programı ve ders tipine göre saat özeti görünür
- **Analiz**: seçilen tarih aralığında, öğretmen/öğrenci bazında ders
  tipine göre toplam saatler
- **Ödemeler**: öğrenci bazında program/birebir ücreti, yapılan ödemeler,
  otomatik hesaplanan kalan borç
- Veriler bilgisayarınızda `%USERPROFILE%\DersProgrami\veri.db` dosyasında
  otomatik saklanır; ayrı kaydet/aç derdi yoktur.

Henüz yok: gerçek sürükle-bırakla program içi taşıma (şu an yerleştirilmiş
bir dersi taşımak için önce kaldırıp sonra yeniden sürüklemeniz gerekir),
yazdırma/Excel'e aktarma.

## Geliştirme ortamında çalıştırma (Linux/Mac/Windows, Python ile)

```bash
pip install -r requirements.txt
cd src
python -m dersprogram.main
```

## Windows için hazır .exe indirme (Python kurmadan)

Her güncellemede `.exe` dosyası GitHub üzerinde otomatik olarak üretilir:

1. Repo sayfasında üstteki **"Actions"** sekmesine git.
2. En üstteki (en yeni) çalışmaya tıkla.
3. Sayfanın altındaki **"Artifacts"** bölümünden **DersProgrami-windows**
   dosyasını indir (bir .zip iner).
4. Zip'i aç, içindeki `DersProgrami.exe` dosyasına çift tıkla.

> Not: GitHub'a giriş yapmış olman gerekir (Artifacts indirmek için).

## Windows için kendi bilgisayarında .exe üretme (alternatif)

`build_windows.bat` dosyasını bir Windows bilgisayarda (Python 3.10+ kurulu
olmalı) çift tıklayarak veya komut satırından çalıştırın. İşlem bitince
`dist\DersProgrami.exe` dosyasını kurumdaki bilgisayara kopyalamanız yeterli;
ayrıca kurulum ya da Python gerekmez.

## Proje yapısı

```
src/dersprogram/
    db.py              veritabanı (SQLite) erişimi - ham CRUD
    scheduling.py       program motoru: hafta hesaplama, şablon+istisna
                         birleştirme, çakışma kontrolü, oto-atama, analiz
    main.py             uygulama giriş noktası
    ui/
        main_window.py     sekmeleri birleştiren ana pencere
        schedule_tab.py    Ana Program: büyük ızgara + sürükle-bırak havuzu
        add_lesson_dialog.py  "Ders Ekle" diyaloğu
        teachers_tab.py    Öğretmenler
        students_tab.py    Öğrenciler
        classes_tab.py     Sınıflar
        analysis_tab.py    Analiz
        payments_tab.py    Ödemeler
        list_tab.py        Ders/Derslik gibi basit liste ekranları
        settings_tab.py    gün/saat ayarları
        widgets.py         ortak bileşenler (hafta gezinme, mini ızgara, özet tablosu)
```
