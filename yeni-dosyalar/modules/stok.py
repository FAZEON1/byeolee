"""Lokasyon bazlı stok durumu."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

LOK_TIP = {
    "ana_depo": "Ana Depo", "toplama": "Toplama", "karantina": "Karantina",
    "iade": "İade", "hasarli": "Hasarlı", "mal_kabul": "Mal Kabul", "sevkiyat": "Sevkiyat",
}


def goster() -> None:
    ui.baslik("Stok Durumu", "lokasyon bazlı")

    df = db.sorgu(
        "stok",
        select="*, urunler(sku,ad), partiler(parti_no,skt,durum), "
               "lokasyonlar(kod,ad,tip), depolar(ad)",
        filtreler=[("fiziksel_miktar", "gt", 0)],
    )
    if df.empty:
        st.info("Stokta ürün yok.")
        return

    def al(sutun, alan):
        return df[sutun].apply(lambda x: (x or {}).get(alan))

    bugun = pd.Timestamp.today().normalize()
    skt = pd.to_datetime(al("partiler", "skt"), errors="coerce")
    pdurum = al("partiler", "durum")
    satilabilir = (
        (pdurum == "kullanilabilir") & (skt.isna() | (skt >= bugun))
    ) * (df["fiziksel_miktar"] - df["rezerve_miktar"])

    t = pd.DataFrame({
        "Lokasyon": al("lokasyonlar", "kod"),
        "Tip": al("lokasyonlar", "tip").map(LOK_TIP),
        "SKU": al("urunler", "sku"),
        "Ürün": al("urunler", "ad").str.slice(0, 40),
        "Parti": al("partiler", "parti_no"),
        "SKT": skt.apply(ui.tarih_bicim),
        "Parti Durumu": pdurum.apply(ui.durum_etiket),
        "Fiziksel": df["fiziksel_miktar"],
        "Rezerve": df["rezerve_miktar"],
        "Satılabilir": satilabilir.clip(lower=0),
    })

    kartlar = [
        {"baslik": "Toplam Fiziksel", "deger": ui.sayi_bicim(t["Fiziksel"].sum()),
         "alt": f"{len(t)} stok satırı", "renk": "lacivert"},
        {"baslik": "Satılabilir", "deger": ui.sayi_bicim(t["Satılabilir"].sum()),
         "alt": "rezerve/bloke düşülmüş", "renk": "yesil"},
        {"baslik": "Rezerve", "deger": ui.sayi_bicim(t["Rezerve"].sum()),
         "alt": "siparişe ayrılmış", "renk": "gri"},
        {"baslik": "Bloke / Karantina",
         "deger": ui.sayi_bicim(t[pdurum != "kullanilabilir"]["Fiziksel"].sum()),
         "alt": "satışa kapalı", "renk": "turuncu"},
    ]
    ui.kpi_satiri(kartlar, sutun=4)

    c1, c2 = st.columns(2)
    tipler = c1.multiselect("Lokasyon tipi", sorted(t["Tip"].dropna().unique()), key="st_tip", placeholder="Tümü")
    lokler = c2.multiselect("Lokasyon", sorted(t["Lokasyon"].dropna().unique()), key="st_lok", placeholder="Tümü")
    if tipler:
        t = t[t["Tip"].isin(tipler)]
    if lokler:
        t = t[t["Lokasyon"].isin(lokler)]

    ui.tablo(t.sort_values("Lokasyon"), anahtar="stok", indir="stok", yukseklik=460, kolonlar={
        "Fiziksel": ui.sayi_kolonu("Fiziksel"),
        "Rezerve": ui.sayi_kolonu("Rezerve"),
        "Satılabilir": ui.sayi_kolonu("Satılabilir"),
    })
