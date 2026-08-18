"""Bildirim merkezi ve günlük SKT kontrolü."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from lib import db, ui


def goster() -> None:
    ui.baslik("Bildirimler", "")
    df = db.sorgu("bildirimler", sira="olusturuldu", tersine=True, limit=300)
    okunmamis = df[~df["okundu"]] if not df.empty else pd.DataFrame()

    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(f"**{len(okunmamis)} okunmamış bildirim**")
    if len(okunmamis) and c2.button("Tümünü okundu işaretle", use_container_width=True):
        db.guncelle("bildirimler",
                    {"okundu": True, "okundu_tarih": datetime.now(timezone.utc).isoformat()},
                    [("okundu", "eq", False)])
        st.rerun()
    if c3.button("⟳ SKT Kontrolü Çalıştır", type="primary", use_container_width=True):
        try:
            s = db.rpc("gunluk_skt_kontrol")
            st.success(f"{s.get('skt_gecen_parti')} parti SKT geçmiş işaretlendi · "
                       f"{s.get('yeni_uyari')} yeni uyarı üretildi.")
            st.rerun()
        except Exception as e:
            st.error(f"Çalıştırılamadı: {e}")

    if df.empty:
        st.info("Bildirim yok.")
        return

    seviye_ikon = {"kritik": "🔴", "uyari": "🟠", "bilgi": "🔵"}
    for _, b in df.head(80).iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([10, 1])
            solgun = "opacity:.55;" if b["okundu"] else ""
            c1.markdown(
                f"<div style='{solgun}'>{seviye_ikon.get(b['seviye'], '🔵')} "
                f"<b>{b['baslik']}</b><br>"
                f"<span style='font-size:.85rem;color:#475569'>{b['mesaj'] or ''}</span><br>"
                f"<span style='font-size:.75rem;color:#94a3b8'>"
                f"{ui.tarih_saat(b['olusturuldu'])}</span></div>",
                unsafe_allow_html=True)
            if not b["okundu"]:
                if c2.button("✓", key=f"bl_{b['id']}", help="Okundu işaretle"):
                    db.guncelle("bildirimler", {
                        "okundu": True,
                        "okundu_tarih": datetime.now(timezone.utc).isoformat()},
                        [("id", "eq", int(b["id"]))])
                    st.rerun()
