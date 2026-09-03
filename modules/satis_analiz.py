"""Satış Analizi — hangi kanalda, hangi modelden kaç adet sattım, ne kazandım.

Veri kaynağı `v_kanal_satis_karlilik`: pazaryeri panel raporlarından gelen
satış özeti ile ithalat modülünden gelen gerçek landed cost birleştirilir.

Kâr hesabı:
    net kâr = (net ciro ÷ KDV) − (komisyon ÷ KDV) − (adet × birim maliyet)

Panel raporundaki tutarlar KDV dahil, ithalat maliyeti KDV hariç olduğu için
ciro ve komisyon ürünün kendi KDV oranıyla arındırılır.

DAHİL DEĞİL: kargo bedeli, platform hizmet bedeli, reklam gideri, stopaj.
Bunlar hakediş (cari hesap ekstresi) verisinden gelir.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

SAYISAL = ["net_satis_adet", "iptal_adet", "iade_adet", "net_ciro", "komisyon_tutari",
           "net_ciro_kdvsiz", "komisyon_kdvsiz", "birim_maliyet_try",
           "toplam_maliyet_try", "net_kar_try", "kar_marji", "iade_orani",
           "ort_satis_fiyati", "ort_komisyon_orani"]


def goster() -> None:
    ui.baslik("Satış Analizi", "kanal · model · kârlılık")
    M = auth.maliyet_gorur()

    df = db.sorgu("v_kanal_satis_karlilik", sira="net_ciro", tersine=True, limit=5000)
    if df.empty:
        st.info("Satış verisi yok. Pazaryeri panel raporlarını yükledikten sonra "
                "bu ekran dolar.")
        return

    df = df.copy()
    for alan in SAYISAL:
        if alan in df.columns:
            df[alan] = pd.to_numeric(df[alan], errors="coerce")

    df = _filtrele(df)
    if df.empty:
        st.info("Filtrelere uyan satış kaydı yok.")
        return

    _kpi(df, M)
    st.markdown("---")

    t1, t2, t3, t4 = st.tabs(
        ["📦 Model Bazında", "🏷️ Marka & Kategori", "📅 Yıl Karşılaştırma", "⚠️ Eksik Maliyet"])

    with t1:
        _model_tablosu(df, M)
    with t2:
        _kirilim(df, M)
    with t3:
        _yillar(df, M)
    with t4:
        _eksik(df)

    st.markdown("---")
    ui.kural_notu(
        "Net kâr = KDV'siz ciro − KDV'siz komisyon − (adet × gerçek ithalat maliyeti). "
        "<b>Kargo, platform hizmet bedeli, reklam ve stopaj bu hesaba dahil değildir</b> — "
        "bunlar hakediş verisinden gelir, gerçek net kârınız buradakinden bir miktar düşüktür."
    )


# ------------------------------------------------------------------- filtreler
def _filtrele(df: pd.DataFrame) -> pd.DataFrame:
    with st.expander("🔎 Filtreler", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        kanallar = sorted(df["kanal"].dropna().unique())
        kanal_sec = c1.multiselect("Kanal", kanallar, key="sa_f_kanal",
                                   placeholder="Tümü")
        yillar = sorted(df["yil"].dropna().unique(), reverse=True)
        yil_sec = c2.multiselect("Yıl", yillar, key="sa_f_yil", placeholder="Tümü")
        markalar = sorted(x for x in df["marka"].dropna().unique())
        marka_sec = c3.multiselect("Marka", markalar, key="sa_f_marka",
                                   placeholder="Tümü")
        kategoriler = sorted(x for x in df["kategori"].dropna().unique())
        kat_sec = c4.multiselect("Kategori", kategoriler, key="sa_f_kat",
                                 placeholder="Tümü")

        c5, c6 = st.columns([3, 1])
        arama = c5.text_input("Ürün adı, SKU veya barkod ara", key="sa_f_ara",
                              placeholder="örn. Balgeum veya 8809035148808")
        c6.markdown("&nbsp;", unsafe_allow_html=True)
        if c6.button("Temizle", key="sa_f_sifirla", use_container_width=True):
            for k in ("sa_f_kanal", "sa_f_yil", "sa_f_marka", "sa_f_kat", "sa_f_ara"):
                st.session_state.pop(k, None)
            st.rerun()

    if kanal_sec:
        df = df[df["kanal"].isin(kanal_sec)]
    if yil_sec:
        df = df[df["yil"].isin(yil_sec)]
    if marka_sec:
        df = df[df["marka"].isin(marka_sec)]
    if kat_sec:
        df = df[df["kategori"].isin(kat_sec)]
    if arama:
        q = arama.lower()
        maske = (df[["urun_adi", "sku", "barkod", "model_kodu"]].astype(str)
                 .apply(lambda s: s.str.lower().str.contains(q, na=False)).any(axis=1))
        df = df[maske]
    return df


# ------------------------------------------------------------------------ KPI
def _kpi(df: pd.DataFrame, M: bool) -> None:
    adet = int(df["net_satis_adet"].sum())
    ciro = float(df["net_ciro"].sum())
    kom = float(df["komisyon_tutari"].sum())
    iade = int(df["iade_adet"].sum())
    brut = adet + iade
    ui.kpi_satiri([
        {"baslik": "Net Satış", "deger": ui.sayi_bicim(adet),
         "alt": f"{df['sku'].nunique()} model", "renk": "lacivert"},
        {"baslik": "Net Ciro", "deger": ui.para0(ciro),
         "alt": "KDV dahil", "renk": "lacivert"},
        {"baslik": "Komisyon", "deger": ui.para0(kom),
         "alt": f"ciro üzerinden %{ui.sayi_bicim(kom / ciro * 100, 1) if ciro else 0}",
         "renk": "kirmizi"},
        {"baslik": "İade", "deger": ui.sayi_bicim(iade),
         "alt": f"%{ui.sayi_bicim(iade / brut * 100, 2) if brut else 0}",
         "renk": "sari" if iade else "gri"},
    ])

    if not M:
        return
    bilinen = df[df["net_kar_try"].notna()]
    kar = float(bilinen["net_kar_try"].sum())
    maliyet = float(bilinen["toplam_maliyet_try"].sum())
    ciro_kdvsiz = float(bilinen["net_ciro_kdvsiz"].sum())
    eksik = int(df["maliyet_bilinmiyor"].sum())
    ui.kpi_satiri([
        {"baslik": "Ciro (KDV'siz)", "deger": ui.para0(ciro_kdvsiz),
         "alt": "kâr hesabının tabanı", "renk": "lacivert"},
        {"baslik": "Mal Maliyeti", "deger": ui.para0(maliyet),
         "alt": "gerçek landed cost", "renk": "turuncu"},
        {"baslik": "Net Kâr", "deger": ui.para0(kar),
         "alt": f"%{ui.sayi_bicim(kar / ciro_kdvsiz * 100, 1) if ciro_kdvsiz else 0} marj",
         "renk": "yesil" if kar > 0 else "kirmizi"},
        {"baslik": "Maliyeti Bilinmeyen", "deger": str(eksik),
         "alt": "kâra dahil edilmedi", "renk": "kirmizi" if eksik else "yesil"},
    ])


# -------------------------------------------------------------- model tablosu
def _model_tablosu(df: pd.DataFrame, M: bool) -> None:
    g = (df.groupby(["sku", "urun_adi", "marka", "set_mi"], dropna=False)
           .agg(adet=("net_satis_adet", "sum"),
                iade=("iade_adet", "sum"),
                ciro=("net_ciro", "sum"),
                komisyon=("komisyon_tutari", "sum"),
                maliyet=("toplam_maliyet_try", "sum"),
                kar=("net_kar_try", "sum"),
                eksik=("maliyet_bilinmiyor", "max"))
           .reset_index())
    g["ort_fiyat"] = g["ciro"] / g["adet"].replace(0, pd.NA)
    g["marj"] = g["kar"] / (g["ciro"] / 1.20).replace(0, pd.NA)
    g = g.sort_values("kar" if M else "ciro", ascending=False)

    t = {
        "SKU": g["sku"],
        "Ürün": g["urun_adi"].astype(str).str.slice(0, 48),
        "Marka": g["marka"],
        "Tip": g["set_mi"].map({True: "📦 Set", False: "Tekil"}),
        "Adet": g["adet"],
        "İade": g["iade"],
        "Ort. Fiyat": g["ort_fiyat"],
        "Ciro": g["ciro"],
    }
    if M:
        t.update({
            "Komisyon": g["komisyon"],
            "Maliyet": g["maliyet"],
            "Net Kâr": g["kar"],
            "Marj %": (g["marj"] * 100).round(1),
            "": g["eksik"].map({True: "⚠️", False: ""}),
        })
    ui.tablo(pd.DataFrame(t), anahtar="sa_model", indir="satis-model-bazinda",
             kolonlar={
                 "Adet": ui.sayi_kolonu("Adet"),
                 "İade": ui.sayi_kolonu("İade"),
                 "Ort. Fiyat": ui.sayi_kolonu("Ort. Fiyat", 0, True),
                 "Ciro": ui.sayi_kolonu("Ciro", 0, True),
                 "Komisyon": ui.sayi_kolonu("Komisyon", 0, True),
                 "Maliyet": ui.sayi_kolonu("Maliyet", 0, True),
                 "Net Kâr": ui.sayi_kolonu("Net Kâr", 0, True),
                 "Marj %": ui.sayi_kolonu("Marj %", 1),
             })

    if M and len(g) > 3:
        c1, c2 = st.columns(2)
        kazandiran = g[g["kar"].notna()].nlargest(5, "kar")
        kaybettiren = g[g["kar"].notna()].nsmallest(5, "kar")
        with c1:
            st.caption("**En çok kazandıran 5 model**")
            ui.yatay_bar(kazandiran[["sku", "kar"]], "sku", "kar")
        with c2:
            st.caption("**En az kazandıran / zarar ettiren 5 model**")
            ui.yatay_bar(kaybettiren[["sku", "kar"]], "sku", "kar", sirala=False)


# ------------------------------------------------------------------- kırılım
def _kirilim(df: pd.DataFrame, M: bool) -> None:
    for alan, baslik in (("marka", "Marka"), ("kategori", "Kategori")):
        g = (df.groupby(alan, dropna=False)
               .agg(model=("sku", "nunique"), adet=("net_satis_adet", "sum"),
                    ciro=("net_ciro", "sum"), komisyon=("komisyon_tutari", "sum"),
                    maliyet=("toplam_maliyet_try", "sum"), kar=("net_kar_try", "sum"))
               .reset_index().sort_values("ciro", ascending=False))
        st.caption(f"**{baslik} bazında**")
        t = {baslik: g[alan].fillna("—"), "Model": g["model"], "Adet": g["adet"],
             "Ciro": g["ciro"]}
        if M:
            t.update({"Komisyon": g["komisyon"], "Maliyet": g["maliyet"],
                      "Net Kâr": g["kar"]})
        ui.tablo(pd.DataFrame(t), anahtar=f"sa_{alan}", arama=False,
                 indir=f"satis-{alan}", kolonlar={
                     "Adet": ui.sayi_kolonu("Adet"),
                     "Ciro": ui.sayi_kolonu("Ciro", 0, True),
                     "Komisyon": ui.sayi_kolonu("Komisyon", 0, True),
                     "Maliyet": ui.sayi_kolonu("Maliyet", 0, True),
                     "Net Kâr": ui.sayi_kolonu("Net Kâr", 0, True),
                 })
        st.markdown("")


# ---------------------------------------------------------------------- yıllar
def _yillar(df: pd.DataFrame, M: bool) -> None:
    g = (df.groupby(["kanal", "yil"], dropna=False)
           .agg(model=("sku", "nunique"), adet=("net_satis_adet", "sum"),
                iade=("iade_adet", "sum"), ciro=("net_ciro", "sum"),
                komisyon=("komisyon_tutari", "sum"),
                maliyet=("toplam_maliyet_try", "sum"), kar=("net_kar_try", "sum"))
           .reset_index().sort_values(["kanal", "yil"]))
    g["ort_fiyat"] = g["ciro"] / g["adet"].replace(0, pd.NA)
    g["marj"] = g["kar"] / (g["ciro"] / 1.20).replace(0, pd.NA)

    t = {"Kanal": g["kanal"], "Yıl": g["yil"].astype(str), "Model": g["model"],
         "Adet": g["adet"], "İade": g["iade"], "Ort. Fiyat": g["ort_fiyat"],
         "Ciro": g["ciro"]}
    if M:
        t.update({"Komisyon": g["komisyon"], "Maliyet": g["maliyet"],
                  "Net Kâr": g["kar"], "Marj %": (g["marj"] * 100).round(1)})
    ui.tablo(pd.DataFrame(t), anahtar="sa_yil", arama=False, indir="satis-yil",
             kolonlar={
                 "Adet": ui.sayi_kolonu("Adet"), "İade": ui.sayi_kolonu("İade"),
                 "Ort. Fiyat": ui.sayi_kolonu("Ort. Fiyat", 0, True),
                 "Ciro": ui.sayi_kolonu("Ciro", 0, True),
                 "Komisyon": ui.sayi_kolonu("Komisyon", 0, True),
                 "Maliyet": ui.sayi_kolonu("Maliyet", 0, True),
                 "Net Kâr": ui.sayi_kolonu("Net Kâr", 0, True),
                 "Marj %": ui.sayi_kolonu("Marj %", 1),
             })
    if len(g) > 1:
        y = g.assign(etiket=g["yil"].astype(str))[["etiket", "ciro"]]
        ui.yatay_bar(y, "etiket", "ciro", sirala=False)


# ------------------------------------------------------------------ eksikler
def _eksik(df: pd.DataFrame) -> None:
    e = df[df["maliyet_bilinmiyor"]]
    if e.empty:
        st.success("Tüm satılan ürünlerin maliyeti biliniyor.")
        return
    g = (e.groupby(["barkod", "urun_adi", "set_mi"], dropna=False)
           .agg(adet=("net_satis_adet", "sum"), ciro=("net_ciro", "sum"))
           .reset_index().sort_values("ciro", ascending=False))
    st.warning(
        f"{len(g)} üründe maliyet bilinmiyor; toplam {ui.sayi_bicim(g['adet'].sum())} "
        f"adet ve {ui.para0(g['ciro'].sum())} ciro kâr hesabının dışında kaldı.",
        icon="⚠️")
    st.caption("**Set** olanlar için Ürün & Stok → Set İçerikleri ekranından bileşen "
               "tanımlayın. **Tekil** olanlar ya katalogda yok ya da hiç ithal edilmemiş.")
    ui.tablo(pd.DataFrame({
        "Barkod / Set Kodu": g["barkod"],
        "Ürün": g["urun_adi"],
        "Tip": g["set_mi"].map({True: "📦 Set", False: "Tekil"}),
        "Adet": g["adet"],
        "Ciro": g["ciro"],
    }), anahtar="sa_eksik", indir="maliyeti-bilinmeyen", kolonlar={
        "Adet": ui.sayi_kolonu("Adet"),
        "Ciro": ui.sayi_kolonu("Ciro", 0, True),
    })
