# Ders Programı

Bir kurumun haftalık ders programını hazırlamak için masaüstü uygulaması.
Windows için, tek kullanıcılı, internete ihtiyaç duymadan (offline) çalışır.

## Özellikler (v1)

- Öğretmen, Ders, Sınıf, Derslik tanımlama
- Sınıf bazında haftalık program ızgarası (gün × ders saati)
- Hücreye çift tıklayarak ders/öğretmen/derslik atama
- Aynı öğretmen ya da dersliğin aynı saatte başka bir sınıfa da
  atanması durumunda otomatik çakışma uyarısı (kırmızı hücre)
- Gün sayısı ve günlük ders saati sayısı ayarlanabilir
- Veriler bilgisayarınızda `Belgelerim` benzeri bir klasörde
  (`%USERPROFILE%\DersProgrami\veri.db`) otomatik saklanır; kaydet/aç
  derdi yoktur, program her açıldığında kaldığı yerden devam eder.

Henüz yok, ileride eklenecek: otomatik program oluşturma (kısıtlamalara göre
algoritmanın programı kendisinin kurması), yazdırma/Excel'e aktarma.

## Geliştirme ortamında çalıştırma (Linux/Mac/Windows, Python ile)

```bash
pip install -r requirements.txt
cd src
python -m dersprogram.main
```

## Windows için .exe üretme

`build_windows.bat` dosyasını bir Windows bilgisayarda (Python 3.10+ kurulu
olmalı) çift tıklayarak veya komut satırından çalıştırın. İşlem bitince
`dist\DersProgrami.exe` dosyasını kurumdaki bilgisayara kopyalamanız yeterli;
ayrıca kurulum ya da Python gerekmez.

> Not: .exe dosyası yalnızca Windows üzerinde üretilebilir (bu geliştirme
> ortamı Linux olduğu için burada üretilemiyor).

## Proje yapısı

```
src/dersprogram/
    db.py            veritabanı (SQLite) erişimi
    main.py           uygulama giriş noktası
    ui/
        main_window.py   sekmeleri birleştiren ana pencere
        list_tab.py       öğretmen/ders/sınıf/derslik liste ekranı
        schedule_tab.py   program ızgarası
        settings_tab.py   gün/saat ayarları
```
