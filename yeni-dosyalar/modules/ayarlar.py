"""Sistem ayarları ve satış kanalları."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from lib import db, ui

AD = {
    "skt_sari_gun": "SKT uyarı eşiği — SARI (gün)",
    "skt_turuncu_gun": "SKT uyarı eşiği — TURUNCU (gün)",
    "skt_kirmizi_gun": "SKT uyarı eşiği — KIRMIZI (gün)",
    "stok_cikis_kurali": "Stok çıkış kuralı (FEFO / FIFO / LIFO)",
    "negatif_stok_izin": "Negatif stoğa izin ver (true/false)",
    "olu_stok_gun": "Ölü stok eşiği (gün)",
    "sa_onay_limiti": "Satın alma onay limiti (₺)",
    "firma_adi": "Firma adı",
    "para_birimi": "Temel para birimi",
    "paketleme_maliyeti": "Sipariş başı paketleme maliyeti (₺)",
}


def goster() -> None:
    ui.baslik("Ayarlar", "sistem parametreleri")
    sol, sag = st.columns(2, gap="medium")

    with sol:
        st.markdown("##### Sistem Ayarları")
        ayarlar = db.sorgu("ayarlar", sira="anahtar")
        if ayarlar.empty:
            st.info("Ayar kaydı yok.")
        else:
            with st.form("ayar_form"):
                yeni = {}
                for r in ayarlar.itertuples():
                    mevcut = str(r.deger).strip('"')
                    yeni[r.anahtar] = st.text_input(
                        AD.get(r.anahtar, r.anahtar), value=mevcut,
                        help=r.aciklama, key=f"ay_{r.anahtar}")
                if st.form_submit_button("Tümünü Kaydet", type="primary"):
                    degisen = 0
                    for r in ayarlar.itertuples():
                        eski = str(r.deger).strip('"')
                        if yeni[r.anahtar] != eski:
                            v = yeni[r.anahtar].strip()
                            deger = v if _sayisal(v) else f'"{v}"'
                            db.guncelle("ayarlar", {
                                "deger": deger,
                                "guncellendi": datetime.now(timezone.utc).isoformat()},
                                [("anahtar", "eq", r.anahtar)])
                            degisen += 1
                    st.success(f"{degisen} ayar güncellendi.")
                    st.rerun()

    with sag:
        st.markdown("##### Satış Kanalları")
        ui.kural_notu(
            "ℹ️ <b>Min. raf ömrü</b>, o kanala satılabilecek partinin en az kaç gün SKT'si "
            "kalmış olması gerektiğini belirler. Bu eşiğin altındaki partiler FEFO tahsisinde "
            "otomatik atlanır (BR-04)."
        )
        kanallar = db.sorgu("kanallar", sira="ad")
        if kanallar.empty:
            st.info("Kanal yok.")
            return
        tablo = pd.DataFrame({
            "id": kanallar["id"], "Kanal": kanallar["ad"], "Kod": kanallar["kod"],
            "Komisyon %": kanallar["komisyon_orani"].astype(float),
            "Min. Raf Ömrü (gün)": kanallar["min_raf_omru_gun"].astype(int),
            "Kargo": kanallar["varsayilan_kargo"].fillna(""),
        })
        duzenlenen = st.data_editor(
            tablo, hide_index=True, width="stretch", key="kanal_ed",
            disabled=["id", "Kanal", "Kod"],
            column_config={
                "id": None,
                "Komisyon %": st.column_config.NumberColumn("Komisyon %", step=0.1),
                "Min. Raf Ömrü (gün)": st.column_config.NumberColumn(
                    "Min. Raf Ömrü (gün)", step=1),
            })
        if st.button("Kanalları Kaydet", type="primary"):
            degisen = 0
            for _, yeni_s in duzenlenen.iterrows():
                eski_s = tablo[tablo["id"] == yeni_s["id"]].iloc[0]
                guncelle = {}
                if float(yeni_s["Komisyon %"]) != float(eski_s["Komisyon %"]):
                    guncelle["komisyon_orani"] = float(yeni_s["Komisyon %"])
                if int(yeni_s["Min. Raf Ömrü (gün)"]) != int(eski_s["Min. Raf Ömrü (gün)"]):
                    guncelle["min_raf_omru_gun"] = int(yeni_s["Min. Raf Ömrü (gün)"])
                if (yeni_s["Kargo"] or "") != (eski_s["Kargo"] or ""):
                    guncelle["varsayilan_kargo"] = yeni_s["Kargo"] or None
                if guncelle:
                    db.guncelle("kanallar", guncelle, [("id", "eq", int(yeni_s["id"]))])
                    degisen += 1
            st.success(f"{degisen} kanal güncellendi.")
            st.rerun()


def _sayisal(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False
