"""Trendyol <-> KAYRAN ERP senkronizasyon işçisi.

Üç iş yapar:
  1. siparis : Trendyol'daki yeni paketleri ERP'ye yazar, FEFO rezervasyonunu tetikler.
  2. stok    : ERP'deki satılabilir stok + fiyatı Trendyol'a gönderir.
  3. durum   : ERP'de toplanan/paketlenen siparişleri Trendyol'da Picking/Invoiced yapar,
               kendi kargonuzu kullanıyorsanız takip numarasını gönderir.

Çalıştırma:
    python -m entegrasyon.senkron                 # ISLEMLER ortam değişkenine göre
    python -m entegrasyon.senkron siparis stok    # sadece belirtilenler

Ortam değişkenleri (GitHub Actions Secrets):
    SUPABASE_URL, SUPABASE_KEY, ERP_KULLANICI, ERP_SIFRE
    TY_SATICI_ID, TY_API_KEY, TY_API_SECRET
İsteğe bağlı:
    TY_TEST=1            Trendyol test (stage) ortamını kullan
    TY_GERIYE_SAAT=24    İlk çalıştırmada kaç saat geriye bakılacağı
    TY_FIYAT_GONDER=1    Stok gönderirken fiyatı da gönder (varsayılan: gönderme)
    TY_FIYAT_TOPLAM=1    Trendyol satır tutarını "toplam" kabul et (varsayılan: birim)
    TY_KENDI_KARGO=1     Takip numarasını biz gönderiyoruz (varsayılan: hayır)
    TY_KURU=1            Kuru deneme: hiçbir yere yazma (ne Trendyol'a ne ERP'ye),
                         sadece oku ve ne olacağını raporla
    ISLEMLER=siparis,stok,durum
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

from entegrasyon.erp import Erp, _cevre
from entegrasyon.trendyol import Trendyol, TrendyolHatasi

KANAL_KOD = "TY"
GUN_MS = 86_400_000


def _bayrak(ad: str, varsayilan: bool = False) -> bool:
    d = os.environ.get(ad)
    if d is None:
        return varsayilan
    return str(d).strip().lower() in ("1", "true", "evet", "yes", "on")


def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def _sayi(d, varsayilan=0.0) -> float:
    try:
        return float(d)
    except (TypeError, ValueError):
        return varsayilan


# ==================================================================== 1) SİPARİŞ
DURUMLAR = ("Created", "Picking")


def _satir_cevir(satir: dict, toplam_mi: bool) -> dict:
    adet = int(_sayi(satir.get("quantity"), 1)) or 1
    tutar = satir.get("amount")
    if tutar is None:
        tutar = satir.get("price")
    tutar = _sayi(tutar)
    birim = round(tutar / adet, 4) if toplam_mi else tutar
    return {
        "barkod": satir.get("barcode"),
        "stok_kodu": satir.get("merchantSku"),
        "kanal_satir_id": satir.get("id"),
        "urun_adi": satir.get("productName"),
        "adet": adet,
        "birim_fiyat": birim,
        "kdv_orani": _sayi(satir.get("vatBaseAmount"), 20),
    }


def _paket_cevir(paket: dict, toplam_mi: bool) -> dict:
    adres = paket.get("shipmentAddress") or {}
    fatura = paket.get("invoiceAddress") or {}
    ad = " ".join(x for x in (paket.get("customerFirstName"),
                              paket.get("customerLastName")) if x).strip()
    tarih = paket.get("orderDate")
    return {
        "kanal_siparis_no": str(paket.get("orderNumber") or paket.get("id")),
        "kanal_paket_id": str(paket.get("id") or ""),
        "musteri_adi": ad or (adres.get("fullName") or "Trendyol Müşterisi"),
        "telefon": adres.get("phone") or "",
        "il": adres.get("city") or "",
        "adres": " ".join(x for x in (adres.get("address1"), adres.get("address2"),
                                      adres.get("district"), adres.get("city")) if x),
        "fatura_adres": " ".join(x for x in (fatura.get("address1"), fatura.get("district"),
                                             fatura.get("city")) if x),
        "siparis_tarihi": (datetime.fromtimestamp(tarih / 1000, timezone.utc).isoformat()
                           if tarih else datetime.now(timezone.utc).isoformat()),
        "kargo_bedeli": 0,
        "kargo_firmasi": paket.get("cargoProviderName") or "",
        "takip_no": str(paket.get("cargoTrackingNumber") or ""),
        "notlar": f"Trendyol paket {paket.get('id')} · durum {paket.get('shipmentPackageStatus') or paket.get('status')}",
        "satirlar": [_satir_cevir(s, toplam_mi) for s in (paket.get("lines") or [])],
    }


def siparisleri_cek(erp: Erp, ty: Trendyol, kanal: dict) -> dict:
    baslangic = datetime.now(timezone.utc)
    geriye = int(_sayi(_cevre("TY_GERIYE_SAAT", "24"), 24))
    toplam_mi = _bayrak("TY_FIYAT_TOPLAM")
    kuru = _bayrak("TY_KURU")

    son = None if kuru else erp.son_basarili_bitis(kanal["id"], "siparis_cek")
    bas = (son - timedelta(minutes=30)) if son else (baslangic - timedelta(hours=geriye))
    # Trendyol tek sorguda en fazla 2 haftalık aralığa izin verir
    if (baslangic - bas).days > 13:
        bas = baslangic - timedelta(days=13)

    okunan = yazilan = atlanan = hatali = 0
    eslesmeyenler: list[dict] = []
    hata_mesaji = None

    try:
        for durum in DURUMLAR:
            for paket in ty.siparisler(_ms(bas), _ms(baslangic), durum=durum):
                okunan += 1
                sip = _paket_cevir(paket, toplam_mi)
                if not sip["satirlar"]:
                    atlanan += 1
                    continue
                if kuru:
                    atlanan += 1
                    print(f"  (kuru) {sip['kanal_siparis_no']} · paket {sip['kanal_paket_id']}"
                          f" · {len(sip['satirlar'])} kalem · "
                          + ", ".join(f"{l['barkod']}×{l['adet']}" for l in sip["satirlar"]))
                    continue
                try:
                    sonuc = erp.siparis_kaydet(kanal["id"], sip)
                    # Aynı sipariş numarası birden fazla pakete bölünmüşse
                    if sonuc.get("durum") == "mukerrer":
                        mevcut = erp.paket_id_ile_siparis(kanal["id"], sip["kanal_siparis_no"])
                        if mevcut and str(mevcut.get("kanal_paket_id") or "") != sip["kanal_paket_id"]:
                            sip["kanal_siparis_no"] = (
                                f"{sip['kanal_siparis_no']}-{sip['kanal_paket_id']}")
                            sonuc = erp.siparis_kaydet(kanal["id"], sip)
                    if sonuc.get("durum") == "eklendi":
                        yazilan += 1
                        eks = sonuc.get("eslesmeyen") or []
                        if eks:
                            eslesmeyenler.append(
                                {"siparis": sip["kanal_siparis_no"], "kodlar": eks})
                        print(f"  + {sip['kanal_siparis_no']} "
                              f"({len(sip['satirlar'])} kalem)"
                              + (f"  ESLESMEYEN: {eks}" if eks else ""))
                    else:
                        atlanan += 1
                except Exception as e:
                    hatali += 1
                    print(f"  ! {sip['kanal_siparis_no']}: {e}")
        basarili = hatali == 0
    except TrendyolHatasi as e:
        basarili, hata_mesaji = False, str(e)
        print(f"  !! Trendyol: {e}")

    # Kuru calisma ayri isim altinda loglanir; yoksa bir sonraki gercek calisma
    # pencereyi kuru calismanin bitisinden baslatip siparisleri atlardi.
    erp.log_yaz(kanal["id"], "siparis_cek_kuru" if kuru else "siparis_cek",
                baslangic, basarili,
                okunan=okunan, yazilan=yazilan, atlanan=atlanan, hatali=hatali,
                detay={"aralik_bas": bas.isoformat(), "kuru": kuru,
                       "eslesmeyen": eslesmeyenler[:50]},
                hata_mesaji=hata_mesaji)
    return {"okunan": okunan, "yazilan": yazilan, "atlanan": atlanan,
            "hatali": hatali, "eslesmeyen": eslesmeyenler}


# ==================================================================== 2) STOK
def stok_gonder(erp: Erp, ty: Trendyol, kanal: dict) -> dict:
    baslangic = datetime.now(timezone.utc)
    fiyat_gonder = _bayrak("TY_FIYAT_GONDER")
    kuru = _bayrak("TY_KURU")

    satirlar = erp.gonderilecek_stok(kanal["id"])
    kalemler, atlanan = [], 0
    for s in satirlar:
        barkod = (s.get("barkod") or "").strip()
        if not barkod:
            atlanan += 1
            continue
        kalem = {"barcode": barkod, "quantity": int(_sayi(s.get("gonderilecek")))}
        if fiyat_gonder:
            sf = _sayi(s.get("satis_fiyati"))
            lf = _sayi(s.get("liste_fiyati")) or sf
            if sf > 0:
                kalem["salePrice"] = round(sf, 2)
                kalem["listPrice"] = round(lf, 2)
        kalemler.append(kalem)

    partiler, hata_mesaji = [], None
    basarili = True
    if kuru:
        print(f"  (kuru çalışma) {len(kalemler)} kalem gönderilecekti, ilk 5: {kalemler[:5]}")
    else:
        try:
            for i in range(0, len(kalemler), 1000):
                dilim = kalemler[i:i + 1000]
                y = ty.stok_fiyat_gonder(dilim)
                partiler.append({"batchRequestId": y.get("batchRequestId"),
                                 "adet": len(dilim)})
                print(f"  → {len(dilim)} kalem gönderildi · parti {y.get('batchRequestId')}")
        except TrendyolHatasi as e:
            basarili, hata_mesaji = False, str(e)
            print(f"  !! Trendyol: {e}")

    erp.log_yaz(kanal["id"], "stok_gonder", baslangic, basarili,
                okunan=len(satirlar), yazilan=0 if kuru else len(kalemler),
                atlanan=atlanan, hatali=0 if basarili else 1,
                detay={"partiler": partiler, "fiyat_gonderildi": fiyat_gonder,
                       "kuru": kuru},
                hata_mesaji=hata_mesaji)
    return {"okunan": len(satirlar), "gonderilen": len(kalemler),
            "atlanan": atlanan, "partiler": partiler}


# ==================================================================== 3) DURUM
def durum_gonder(erp: Erp, ty: Trendyol, kanal: dict) -> dict:
    baslangic = datetime.now(timezone.utc)
    kuru = _bayrak("TY_KURU")
    kendi_kargo = _bayrak("TY_KENDI_KARGO")

    bekleyenler = erp.bildirim_bekleyenler(kanal["id"])
    yazilan = atlanan = hatali = 0

    for s in bekleyenler:
        paket_id = s.get("kanal_paket_id")
        satirlar = [{"lineId": x["kanal_satir_id"], "quantity": int(_sayi(x["adet"]))}
                    for x in (s.get("satirlar") or []) if x.get("kanal_satir_id")]
        if not paket_id or not satirlar:
            atlanan += 1
            continue

        mevcut = (s.get("kanal_bildirim_durumu") or "").lower()
        erp_durum = s.get("durum")
        if erp_durum in ("paketlendi", "kargoya_verildi"):
            hedef = "Invoiced"
        elif erp_durum == "toplamada":
            hedef = "Picking"
        else:
            atlanan += 1
            continue
        if mevcut == hedef.lower() or (hedef == "Picking" and mevcut in ("picking", "invoiced")):
            atlanan += 1
            continue

        if kuru:
            print(f"  (kuru) {s['siparis_no']} → {hedef}")
            atlanan += 1
            continue

        try:
            # Invoiced'a geçmeden önce Picking zorunlu
            if hedef == "Invoiced" and mevcut != "picking":
                ty.paket_durumu(paket_id, satirlar, durum="Picking")
                erp.bildirim_isle(s["siparis_id"], "picking")
            ty.paket_durumu(paket_id, satirlar, durum=hedef,
                            fatura_no=s.get("siparis_no"))
            if kendi_kargo and s.get("takip_no"):
                ty.takip_no_gonder(paket_id, s["takip_no"])
            erp.bildirim_isle(s["siparis_id"], hedef.lower())
            yazilan += 1
            print(f"  → {s['siparis_no']} → {hedef}")
        except Exception as e:
            hatali += 1
            erp.bildirim_isle(s["siparis_id"], "hata", str(e))
            print(f"  ! {s['siparis_no']}: {e}")

    erp.log_yaz(kanal["id"], "durum_gonder", baslangic, hatali == 0,
                okunan=len(bekleyenler), yazilan=yazilan,
                atlanan=atlanan, hatali=hatali, detay={"kuru": kuru})
    return {"okunan": len(bekleyenler), "yazilan": yazilan,
            "atlanan": atlanan, "hatali": hatali}


# ==================================================================== ana akış
ISLER = {"siparis": siparisleri_cek, "stok": stok_gonder, "durum": durum_gonder}


def main(argv: list[str]) -> int:
    istenen = [a.strip().lower() for a in argv if a.strip()]
    if not istenen:
        istenen = [a.strip().lower() for a in
                   _cevre("ISLEMLER", "siparis,stok,durum").split(",") if a.strip()]
    bilinmeyen = [i for i in istenen if i not in ISLER]
    if bilinmeyen:
        print(f"Bilinmeyen işlem: {bilinmeyen}. Geçerli: {list(ISLER)}")
        return 2

    print(f"KAYRAN ERP · Trendyol senkronizasyonu · "
          f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    print(f"İşlemler: {', '.join(istenen)}"
          + ("   [KURU ÇALIŞMA — Trendyol'a yazma yapılmaz]" if _bayrak("TY_KURU") else ""))

    erp = Erp()
    ty = Trendyol(_cevre("TY_SATICI_ID", zorunlu=True),
                  _cevre("TY_API_KEY", zorunlu=True),
                  _cevre("TY_API_SECRET", zorunlu=True),
                  test=_bayrak("TY_TEST"))
    kanal = erp.kanal(KANAL_KOD)
    print(f"Kanal: {kanal['ad']} (id {kanal['id']}, "
          f"min raf ömrü {kanal['min_raf_omru_gun']} gün)\n")

    kod = 0
    try:
        for isim in istenen:
            print(f"[{isim}]")
            try:
                ozet = ISLER[isim](erp, ty, kanal)
                print(f"  özet: {ozet}\n")
            except SystemExit:
                raise
            except Exception as e:
                kod = 1
                print(f"  !! {isim} başarısız: {e}")
                traceback.print_exc()
                erp.log_yaz(kanal["id"], isim, datetime.now(timezone.utc), False,
                            hatali=1, hata_mesaji=str(e))
    finally:
        erp.kapat()
    print("Bitti." if kod == 0 else "Hatalarla bitti.")
    return kod


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
