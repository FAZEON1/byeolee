"""Kullanıcı ve rol yönetimi."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Kullanıcılar", "rol ve yetki")
    ui.kural_notu(
        "🔑 <b>Yetkiler veritabanı seviyesinde (RLS) uygulanır.</b> Maliyet, kâr marjı ve cari "
        "bakiye alanları yetkisiz rollerde tüm ekran, rapor ve görünümlerde "
        "<b>veritabanı tarafından NULL döner</b> — arayüzde gizlenmekle kalmaz (BR-14).<br>"
        "Yeni kullanıcı eklemek için Supabase panelinden davet gönderin; profil otomatik oluşur."
    )

    df = db.sorgu("profiller", sira="ad_soyad")
    if df.empty:
        st.info("Kullanıcı yok.")
        return

    tablo = pd.DataFrame({
        "id": df["id"],
        "Ad Soyad": df["ad_soyad"],
        "E-posta": df["eposta"],
        "Rol": df["rol"],
        "Aktif": df["aktif"],
        "Maliyet Görür": df["rol"].apply(lambda r: r in auth.YETKI["maliyet"]),
        "Son Giriş": df["son_giris"].apply(ui.tarih_saat),
    })
    duzenlenen = st.data_editor(
        tablo, hide_index=True, width="stretch", key="kul_ed",
        disabled=["id", "Ad Soyad", "E-posta", "Maliyet Görür", "Son Giriş"],
        column_config={
            "id": None,
            "Rol": st.column_config.SelectboxColumn("Rol", options=list(auth.ROL_AD)),
            "Aktif": st.column_config.CheckboxColumn("Aktif"),
        })
    if st.button("Değişiklikleri Kaydet", type="primary"):
        degisen = 0
        for _, yeni in duzenlenen.iterrows():
            eski = tablo[tablo["id"] == yeni["id"]].iloc[0]
            guncelle = {}
            if yeni["Rol"] != eski["Rol"]:
                guncelle["rol"] = yeni["Rol"]
            if bool(yeni["Aktif"]) != bool(eski["Aktif"]):
                guncelle["aktif"] = bool(yeni["Aktif"])
            if guncelle:
                db.guncelle("profiller", guncelle, [("id", "eq", yeni["id"])])
                degisen += 1
                if yeni["id"] == db.kullanici_id() and "rol" in guncelle:
                    st.session_state.rol = guncelle["rol"]
        st.success(f"{degisen} kullanıcı güncellendi.")
        st.rerun()

    st.markdown("##### Rol Yetki Matrisi")
    basliklar = {"maliyet": "Maliyet", "katalog": "Katalog", "depo": "Depo",
                 "satinalma": "Satın Alma", "satis": "Satış", "finans": "Finans",
                 "sistem": "Sistem", "onay": "Onay"}
    matris = pd.DataFrame([
        {"Rol": ad, **{basliklar[k]: ("✓" if r in auth.YETKI[k] else "—")
                       for k in auth.YETKI}}
        for r, ad in auth.ROL_AD.items()
    ])
    st.dataframe(matris, hide_index=True, width="stretch")
