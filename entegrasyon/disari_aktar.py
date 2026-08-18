"""Trendyol ürün kataloğunu SALT OKUMA ile JSON dosyasına aktarır.

Bu betik Trendyol'da hiçbir değişiklik yapmaz — yalnızca GET isteği atar.
Amaç: ERP kataloğunu gerçek ürünlerle kurabilmek için Trendyol'daki
ürünlerin bir anlık görüntüsünü almak.

Çalıştırma:
    python -m entegrasyon.disari_aktar

Ortam değişkenleri:
    TY_SATICI_ID, TY_API_KEY, TY_API_SECRET   (zorunlu)
    TY_TEST=1                                  (isteğe bağlı, stage ortamı)
    TY_ARSIVLI=1                               (arşivlenmiş ürünler de gelsin)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from entegrasyon.erp import _cevre
from entegrasyon.trendyol import Trendyol

HEDEF = pathlib.Path("veri")

# ERP kataloğunu kurmak için gereken alanlar. Trendyol'un döndürdüğü diğer
# alanlar (uzun açıklama, öznitelik listesi vb.) depoyu şişirmemek için alınmaz.
ALANLAR = (
    "barcode", "title", "productMainId", "stockCode", "brand", "brandId",
    "categoryName", "pimCategoryId", "quantity", "listPrice", "salePrice",
    "vatRate", "dimensionalWeight", "stockUnitType", "productContentId",
    "approved", "archived", "onSale", "hasActiveCampaign", "createDateTime",
    "lastUpdateDate", "productUrl",
)


def _bayrak(ad: str) -> bool:
    return str(os.environ.get(ad, "")).strip().lower() in ("1", "true", "evet", "yes", "on")


def _sadelestir(u: dict) -> dict:
    kayit = {a: u.get(a) for a in ALANLAR}
    gorseller = u.get("images") or []
    kayit["gorsel"] = (gorseller[0] or {}).get("url") if gorseller else None
    kayit["gorsel_sayisi"] = len(gorseller)
    return kayit


def main() -> int:
    ty = Trendyol(
        _cevre("TY_SATICI_ID", zorunlu=True),
        _cevre("TY_API_KEY", zorunlu=True),
        _cevre("TY_API_SECRET", zorunlu=True),
        test=_bayrak("TY_TEST"),
    )

    ham = list(ty.urunler(arsivli_dahil=_bayrak("TY_ARSIVLI")))
    print(f"Trendyol'dan okunan ürün sayısı: {len(ham)}")
    if not ham:
        print("UYARI: Katalog boş döndü. Satıcı ID veya yetkileri kontrol edin.")
        return 1

    print("\nÖrnek ham kayıt (alan adlarını görmek için):")
    print(json.dumps(ham[0], ensure_ascii=False)[:3000])

    kayitlar = [_sadelestir(u) for u in ham]
    kayitlar.sort(key=lambda k: (k.get("barcode") or ""))

    HEDEF.mkdir(exist_ok=True)
    yol = HEDEF / "trendyol-urunler.json"
    yol.write_text(json.dumps(kayitlar, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\nYazıldı: {yol} ({len(kayitlar)} ürün, {yol.stat().st_size} bayt)")

    onayli = sum(1 for k in kayitlar if k.get("approved"))
    stoklu = sum(1 for k in kayitlar if (k.get("quantity") or 0) > 0)
    print(f"Onaylı: {onayli} · Stoğu olan: {stoklu}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
