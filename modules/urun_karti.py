"""Ürün Kartı — bir ürünle ilgili her şey tek ekranda.

İthalat geçmişi (gerçek landed cost), satış geçmişi, stok ve parti durumu.

Maliyet kaynağı `v_urun_ithalat_ozet`; bu da `ithalat_kalemleri.birim_landed_try`
üzerinden hesaplanır. Geçmiş ithalatlar salt maliyet kaydı olarak yüklendiği için
partilere bağlı değildir; bu yüzden maliyet partilerden değil ithalattan okunur.

Kârlılık uyarısı: buradaki brüt kâr pazaryeri komisyonunu ve kargoyu İÇERMEZ.
Net kâr için Finans → Hakediş & Komisyon ekranındaki veri gerekir.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Ürün Kartı", "ithalat · maliyet · satış · stok")
    M = auth.maliyet_gorur()

    kart = db.sorgu("v_urun_karti", sira="sku")
    if kart.empty:
        st.info("Katalogda ürün yok.")
        return

    secenekler = {
        int(r.urun_id): f"{r.sku} — {r.urun_adi}"
        for r in kart.itertuples()
    }
    secili = ui.secim_kutusu("Ürün", secenekler, "uk_secim", bos="— Ürün seçin —")
    if not secili:
        _liste(kart, M)
        return

    u = kart[kart["urun_id"] == int(secili)].iloc[0]
    _detay(u, M)


# --------------------------------------------------------------------- liste
def _liste(kart: pd.DataFrame, M: bool) -> None:
    st.caption("Ürün seçmeden genel tabloyu görüyorsunuz. Satır sayısı: "
               f"{len(kart)}")
    kolonlar = {
        "SKU": kart["sku"], "Ürün": kart["urun_adi"], "Marka": kart["marka"],
        "Stok": kart["fiziksel"], "Satılabilir": kart["satilabilir"],
        "İthalat": kart["ithalat_sayisi"], "Satılan": kart["satilan_adet"],
    }
    if M:
        kolonlar["Ort. Maliyet ₺"] = kart["ort_birim_maliyet_try"]
        kolonlar["Stok Değeri ₺"] = kart["stok_degeri_try"]
        kolonlar["Brüt Kâr ₺"] = kart["brut_kar_try"]
    ui.tablo(pd.DataFrame(kolonlar), anahtar="uk_liste", indir="urun-karti-ozet")


# --------------------------------------------------------------------- detay
def _detay(u: pd.Series, M: bool) -> None:
    st.markdown(f"### {u['sku']} — {u['urun_adi']}")
    alt = " · ".join(str(x) for x in [u.get("marka"), u.get("kategori"),
                                      ui.durum_etiket(u.get("durum"))] if x)
    st.caption(alt)

    kartlar = [
        {"baslik": "Fiziksel Stok", "deger": ui.sayi_bicim(u["fiziksel"]),
         "alt": f"{ui.sayi_bicim(u['rezerve'])} rezerve", "renk": "lacivert"},
        {"baslik": "Satılabilir", "deger": ui.sayi_bicim(u["satilabilir"]),
         "alt": f"{int(u['parti_sayisi'] or 0)} parti", "renk": "yesil"},
        {"baslik": "Toplam İthal", "deger": ui.sayi_bicim(u["toplam_ithal_adet"]),
         "alt": f"{int(u['ithalat_sayisi'] or 0)} ithalat", "renk": "gri"},
        {"baslik": "Toplam Satış", "deger": ui.sayi_bicim(u["satilan_adet"]),
         "alt": f"{int(u['siparis_sayisi'] or 0)} sipariş", "renk": "turuncu"},
    ]
    ui.kpi_satiri(kartlar)

    if M:
        marj = u.get("birim_marj_try")
        ui.kpi_satiri([
            {"baslik": "Ort. Birim Maliyet", "deger": ui.para(u.get("ort_birim_maliyet_try")),
             "alt": "ağırlıklı ortalama landed cost", "renk": "lacivert"},
            {"baslik": "Son İthalat Maliyeti", "deger": ui.para(u.get("son_birim_maliyet_try")),
             "alt": (f"${ui.sayi_bicim(u.get('son_birim_maliyet_usd'), 4)}"
                     if pd.notna(u.get("son_birim_maliyet_usd")) else ""),
             "renk": "gri"},
            {"baslik": "Stok Değeri", "deger": ui.para0(u.get("stok_degeri_try")),
             "alt": "maliyet üzerinden", "renk": "yesil"},
            {"baslik": "Birim Marj", "deger": ui.para(marj) if pd.notna(marj) else "—",
             "alt": "ort. satış − ort. maliyet",
             "renk": "yesil" if (pd.notna(marj) and marj > 0) else "kirmizi"},
        ])

    st.markdown("---")
    t1, t2, t3 = st.tabs(["🚢 İthalat Geçmişi", "🧾 Satış & Kârlılık", "📋 Künye"])

    # ------------------------------------------------------------ ithalat
    with t1:
        g = db.sorgu("v_urun_ithalat_gecmisi",
                     filtreler=[("urun_id", "eq", int(u["urun_id"]))],
                     sira="ithalat_tarihi", tersine=True)
        if g.empty:
            st.info("Bu ürün için ithalat kaydı yok.")
        else:
            if M:
                st.caption(
                    f"En düşük birim maliyet {ui.para(u.get('en_dusuk_birim_try'))} · "
                    f"en yüksek {ui.para(u.get('en_yuksek_birim_try'))} · "
                    f"ilk ithalat {ui.tarih_bicim(u.get('ilk_ithalat'))} · "
                    f"son tedarikçi {u.get('son_tedarikci') or '—'}")
            tablo = {
                "Tarih": g["ithalat_tarihi"],
                "Dosya": g["dosya_no"],
                "Tedarikçi": g["tedarikci"],
                "Adet": g["adet"],
            }
            if M:
                tablo.update({
                    "Birim FOB": g["birim_fob"],
                    "Mal Bedeli ₺": g["mal_bedeli_try"],
                    "Dağıtılan Masraf ₺": g["dagitilan_masraf_try"],
                    "Binen %": g["binen_masraf_orani"],
                    "Birim Landed ₺": g["birim_landed_try"],
                    "Birim Landed $": g["birim_landed_usd"],
                })
            ui.tablo(pd.DataFrame(tablo), anahtar="uk_ith",
                     indir=f"ithalat-{u['sku']}")

            if M and len(g) > 1:
                st.caption("Birim maliyetin ithalattan ithalata seyri:")
                seri = g[["ithalat_tarihi", "birim_landed_try"]].copy()
                seri["ithalat_tarihi"] = pd.to_datetime(seri["ithalat_tarihi"],
                                                        errors="coerce")
                seri["birim_landed_try"] = pd.to_numeric(seri["birim_landed_try"],
                                                          errors="coerce")
                seri = seri.dropna().sort_values("ithalat_tarihi")
                ui.zaman_serisi(seri, "ithalat_tarihi", "birim_landed_try")

    # ------------------------------------------------------------ satış
    with t2:
        if not u["satilan_adet"]:
            st.info("Bu ürün için satış kaydı yok.")
        else:
            st.markdown(
                f"**{ui.sayi_bicim(u['satilan_adet'])} adet** satılmış "
                f"({ui.sayi_bicim((u.get('satis_orani') or 0) * 100, 1)}% — "
                f"ithal edilenin oranı), "
                f"ilk satış {ui.tarih_bicim(u.get('ilk_satis'))}, "
                f"son satış {ui.tarih_bicim(u.get('son_satis'))}.")
            if M:
                ui.kpi_satiri([
                    {"baslik": "Ciro", "deger": ui.para0(u.get("ciro_try")),
                     "alt": "KDV dahil satır toplamı", "renk": "lacivert"},
                    {"baslik": "Satılan Malın Maliyeti",
                     "deger": ui.para0((u.get("ciro_try") or 0) - (u.get("brut_kar_try") or 0)),
                     "alt": "", "renk": "turuncu"},
                    {"baslik": "Brüt Kâr", "deger": ui.para0(u.get("brut_kar_try")),
                     "alt": f"%{ui.sayi_bicim((u.get('brut_kar_marji') or 0) * 100, 1)} marj",
                     "renk": "yesil" if (u.get("brut_kar_try") or 0) > 0 else "kirmizi"},
                    {"baslik": "Ort. Satış Fiyatı",
                     "deger": ui.para(u.get("ort_satis_fiyati")), "alt": "", "renk": "gri"},
                ])
                ui.kural_notu(
                    "Buradaki brüt kâr <b>pazaryeri komisyonunu, kargoyu ve iadeleri "
                    "içermez</b>. Gerçek net kâr için Finans → Hakediş & Komisyon "
                    "ekranındaki Trendyol hakediş verisi gerekir."
                )

    # ------------------------------------------------------------ künye
    with t3:
        bilgi = {
            "SKU": u["sku"],
            "Ürün Adı": u["urun_adi"],
            "Marka / Kategori": f"{u.get('marka') or '—'} · {u.get('kategori') or '—'}",
            "Durum": ui.durum_etiket(u.get("durum")),
            "Liste Fiyatı": ui.para(u.get("liste_fiyati")),
            "Min. Stok / Sipariş Noktası":
                f"{ui.sayi_bicim(u.get('min_stok'))} / {ui.sayi_bicim(u.get('yeniden_siparis_nokta'))}",
            "En Yakın SKT": ui.tarih_bicim(u.get("en_yakin_skt")),
            "Parti Sayısı": ui.sayi_bicim(u.get("parti_sayisi")),
            "Son Tedarikçi": u.get("son_tedarikci") or "—",
        }
        st.dataframe(
            pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
            hide_index=True, width="stretch")

        if (u.get("yeniden_siparis_nokta") or 0) > 0 and \
           (u.get("satilabilir") or 0) <= (u.get("yeniden_siparis_nokta") or 0):
            st.warning(
                f"Satılabilir stok ({ui.sayi_bicim(u['satilabilir'])}) sipariş "
                f"noktasının ({ui.sayi_bicim(u['yeniden_siparis_nokta'])}) altında. "
                "Yeni ithalat planlanmalı.", icon="⚠️")
