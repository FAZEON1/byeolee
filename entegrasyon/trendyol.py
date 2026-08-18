"""Trendyol Marketplace API istemcisi.

Doğrulanmış uç noktalar (Ağustos 2026):
  Sipariş çekme : GET  /integration/order/sellers/{id}/v2/orders
  Paket durumu  : PUT  /integration/order/sellers/{id}/shipment-packages/{paketId}
  Takip no      : PUT  /integration/order/sellers/{id}/shipment-packages/{paketId}/tracking-details
  Stok/fiyat    : POST /integration/inventory/sellers/{id}/products/price-and-inventory
  Ürün listesi  : GET  /integration/product/sellers/{id}/products   (salt okuma)

Kritik iki kural:
  * User-Agent ZORUNLU. Formatı "{saticiId} - SelfIntegration". Yoksa 403 döner.
  * Hız sınırı 10 saniyede 50 istek. Aşılırsa 429 döner.
"""
from __future__ import annotations

import base64
import time
from collections import deque

import requests

PROD = "https://apigw.trendyol.com"
STAGE = "https://stageapigw.trendyol.com"

# 10 saniyede 50 istek sınırı; güvenlik payıyla 40'ta tutuyoruz
PENCERE_SANIYE = 10.0
PENCERE_LIMIT = 40


class TrendyolHatasi(Exception):
    pass


class Trendyol:
    def __init__(self, satici_id: str, api_key: str, api_secret: str,
                 test: bool = False, zaman_asimi: int = 40):
        self.satici_id = str(satici_id).strip()
        self.taban = STAGE if test else PROD
        self.zaman_asimi = zaman_asimi
        yetki = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self.oturum = requests.Session()
        self.oturum.headers.update({
            "Authorization": f"Basic {yetki}",
            # Kendi yazılımımız olduğu için "SelfIntegration"
            "User-Agent": f"{self.satici_id} - SelfIntegration",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._istekler: deque[float] = deque()

    # ---------------------------------------------------------------- altyapı
    def _hiz_sinirla(self) -> None:
        simdi = time.monotonic()
        while self._istekler and simdi - self._istekler[0] > PENCERE_SANIYE:
            self._istekler.popleft()
        if len(self._istekler) >= PENCERE_LIMIT:
            bekle = PENCERE_SANIYE - (simdi - self._istekler[0]) + 0.15
            if bekle > 0:
                time.sleep(bekle)
            return self._hiz_sinirla()
        self._istekler.append(time.monotonic())

    def _istek(self, metot: str, yol: str, deneme: int = 3, **kw):
        url = self.taban + yol
        son_hata = None
        for i in range(deneme):
            self._hiz_sinirla()
            try:
                y = self.oturum.request(metot, url, timeout=self.zaman_asimi, **kw)
            except requests.RequestException as e:
                son_hata = f"Bağlantı hatası: {e}"
                time.sleep(2 ** i)
                continue

            if y.status_code == 429:                      # hız sınırı
                time.sleep(5 * (i + 1))
                son_hata = "429 too.many.requests"
                continue
            if y.status_code == 403:
                raise TrendyolHatasi(
                    "403 — User-Agent reddedildi. Satıcı ID doğru mu? "
                    f"Gönderilen: '{self.oturum.headers['User-Agent']}'")
            if y.status_code == 401:
                raise TrendyolHatasi("401 — API Key/Secret hatalı veya yetkisiz.")
            if y.status_code >= 500:
                son_hata = f"{y.status_code} sunucu hatası"
                time.sleep(2 ** i)
                continue
            if not y.ok:
                raise TrendyolHatasi(f"{y.status_code} — {y.text[:400]}")
            if not y.content:
                return {}
            try:
                return y.json()
            except ValueError:
                return {"ham": y.text}
        raise TrendyolHatasi(f"{deneme} denemede başarısız: {son_hata}")

    # ---------------------------------------------------------------- siparişler
    def siparisler(self, baslangic_ms: int, bitis_ms: int, durum: str = "Created",
                   sayfa_boyu: int = 50):
        """Belirtilen aralıktaki paketleri sayfa sayfa döndürür (generator)."""
        sayfa = 0
        while True:
            veri = self._istek(
                "GET", f"/integration/order/sellers/{self.satici_id}/v2/orders",
                params={
                    "startDate": baslangic_ms, "endDate": bitis_ms,
                    "status": durum, "page": sayfa, "size": sayfa_boyu,
                    "orderByField": "PackageLastModifiedDate",
                    "orderByDirection": "DESC",
                })
            icerik = veri.get("content") or []
            for paket in icerik:
                yield paket
            toplam_sayfa = veri.get("totalPages") or 0
            sayfa += 1
            if sayfa >= toplam_sayfa or not icerik:
                break

    # ---------------------------------------------------------------- ürün kataloğu
    def urunler(self, sayfa_boyu: int = 200, arsivli_dahil: bool = False):
        """Satıcının Trendyol ürün kataloğunu sayfa sayfa döndürür (generator).

        SALT OKUMA — Trendyol'da hiçbir değişiklik yapmaz.
        """
        sayfa = 0
        while True:
            veri = self._istek(
                "GET", f"/integration/product/sellers/{self.satici_id}/products",
                params={"page": sayfa, "size": sayfa_boyu,
                        "archived": "true" if arsivli_dahil else "false"})
            icerik = veri.get("content") or []
            for urun in icerik:
                yield urun
            toplam_sayfa = veri.get("totalPages") or 0
            sayfa += 1
            if sayfa >= toplam_sayfa or not icerik:
                break

    # ---------------------------------------------------------------- paket durumu
    def paket_durumu(self, paket_id: int, satirlar: list[dict],
                     durum: str = "Picking", fatura_no: str | None = None):
        """durum: 'Picking' veya 'Invoiced'. Önce Picking, sonra Invoiced gönderilir.
        satirlar: [{'lineId': 123, 'quantity': 2}, ...]"""
        gövde = {
            "lines": [{"lineId": int(s["lineId"]), "quantity": int(s["quantity"])}
                      for s in satirlar],
            "params": {"invoiceNumber": fatura_no} if (durum == "Invoiced" and fatura_no) else {},
            "status": durum,
        }
        return self._istek(
            "PUT",
            f"/integration/order/sellers/{self.satici_id}/shipment-packages/{paket_id}",
            json=gövde)

    def takip_no_gonder(self, paket_id: int, takip_no: str):
        """Yalnızca kendi anlaşmalı kargonuzu kullanıyorsanız gerekir.
        Trendyol'un kargosuyla çalışıyorsanız takip no zaten siparişle gelir."""
        return self._istek(
            "PUT",
            f"/integration/order/sellers/{self.satici_id}"
            f"/shipment-packages/{paket_id}/tracking-details",
            json={"trackingNumber": str(takip_no)})

    # ---------------------------------------------------------------- stok / fiyat
    def stok_fiyat_gonder(self, kalemler: list[dict]):
        """kalemler: [{'barcode':..,'quantity':..,'salePrice':..,'listPrice':..}]
        Tek istekte en fazla 1000 kalem. batchRequestId döner."""
        if len(kalemler) > 1000:
            raise TrendyolHatasi("Tek istekte en fazla 1000 kalem gönderilebilir.")
        return self._istek(
            "POST",
            f"/integration/inventory/sellers/{self.satici_id}/products/price-and-inventory",
            json={"items": kalemler})

    def parti_sonucu(self, batch_id: str):
        return self._istek(
            "GET",
            f"/integration/product/sellers/{self.satici_id}/products/batch-requests/{batch_id}")
