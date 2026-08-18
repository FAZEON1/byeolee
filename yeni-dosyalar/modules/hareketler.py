"""Stok hareket defteri — değiştirilemez kayıt."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Stok Hareketleri", "değiştirilemez defter")
    M = auth.maliyet_gorur()

    ui.kural_notu(
        "🔒 <b>Bu defter değiştirilemez ve silinemez (BR-06).</b> Hatalı bir hareket ancak "
        "ters kayıt ile iptal edilir — veritabanı seviyesinde UPDATE ve DELETE engellenmiştir."
    )

    df = db.sorgu(
        "stok_hareket", select="*, urunler(sku,ad), partiler(parti_no,skt)",
        sira="tarih", tersine=True, limit=1500,
    )
    if df.empty:
        st.info("Hareket kaydı yok.")
        return

    t = pd.DataFrame({
        "Tarih": df["tarih"].apply(ui.tarih_saat),
        "Hareket": df["tip"].map(ui.HAREKET_AD).fillna(df["tip"]),
        "SKU": df["urunler"].apply(lambda x: (x or {}).get("sku")),
        "Ürün": df["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 36),
        "Parti": df["partiler"].apply(lambda x: (x or {}).get("parti_no")),
        "Miktar": df["miktar"],
        "FEFO dışı": df["fefo_istisna"].apply(lambda x: "⚠️" if x else ""),
        "Referans": df["referans_tip"].fillna("—"),
        "Açıklama": df["aciklama"].fillna("").str.slice(0, 48),
    })
    if M:
        t.insert(6, "Birim Maliyet", df["birim_maliyet"])

    c1, c2 = st.columns(2)
    tipler = c1.multiselect("Hareket tipi", sorted(t["Hareket"].dropna().unique()), key="hr_tip", placeholder="Tümü")
    yon = c2.radio("Yön", ["Tümü", "Giriş", "Çıkış"], horizontal=True, key="hr_yon")
    if tipler:
        t = t[t["Hareket"].isin(tipler)]
    if yon == "Giriş":
        t = t[t["Miktar"] > 0]
    elif yon == "Çıkış":
        t = t[t["Miktar"] < 0]

    ui.tablo(t, anahtar="hareket", indir="stok-hareketleri", yukseklik=520, kolonlar={
        "Miktar": ui.sayi_kolonu("Miktar", 2),
        "Birim Maliyet": ui.sayi_kolonu("Birim Maliyet", 2, True),
    })
