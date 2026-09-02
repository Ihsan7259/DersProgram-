"""Paketin dışında, bağımsız başlatma betiği.

PyInstaller (ve doğrudan `python main.py` gibi çağrılar) main.py'yi
'dersprogram' paketinin bir parçası olarak değil, tek başına bir betik
olarak çalıştırıyor; bu da main.py içindeki 'from .db import Database'
gibi göreceli import'ları kırıyor ("attempted relative import with no
known parent package"). Bu betik paketin DIŞINDA durduğu için
'dersprogram'ı normal bir paket olarak import eder, sorunu çözer.
"""
from dersprogram.main import main

if __name__ == "__main__":
    raise SystemExit(main())
