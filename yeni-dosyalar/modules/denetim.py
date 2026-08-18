"""Denetim izi — kim, ne zaman, neyi değiştirdi."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from lib import db, ui

ISLEM = {"INSERT": "Oluşturma", "UPDATE": "Güncelleme", "DELETE": "Silme"}
ISLEM_IKON = {"INSERT": "🟢", "UPDATE": "🔵", "DELETE": "🔴"}


def goster() -> None:
    ui.baslik("Denetim İzi", "kim, ne zaman, neyi değiştirdi")
    ui.kural_notu(
        "🛡️ <b>Denetim izi silinemez.</b> Ürün, parti, sipariş, ithalat, masraf, kullanıcı ve "
        "ayar tablolarındaki tüm değişiklikler eski/yeni değerleriyle kaydedilir (FR-11.05)."
    )

    df = db.sorgu("denetim_izi", sira="tarih", tersine=True, limit=600)
    if df.empty:
        st.info("Denetim kaydı yok.")
        return
    prof = db.sorgu("profiller", select="id,ad_soyad")
    harita = dict(zip(prof["id"], prof["ad_soyad"])) if not prof.empty else {}

    c1, c2 = st.columns(2)
    tablolar = c1.multiselect("Tablo", sorted(df["tablo"].unique()), key="dn_tablo", placeholder="Tümü")
    islemler = c2.multiselect("İşlem", sorted(df["islem"].unique()),
                              format_func=lambda i: ISLEM.get(i, i), key="dn_islem", placeholder="Tümü")
    f = df
    if tablolar:
        f = f[f["tablo"].isin(tablolar)]
    if islemler:
        f = f[f["islem"].isin(islemler)]

    t = pd.DataFrame({
        "Tarih": f["tarih"].apply(ui.tarih_saat),
        "Kullanıcı": f["kullanici"].apply(
            lambda k: harita.get(k, "—") if k else "sistem"),
        "Tablo": f["tablo"],
        "Kayıt": f["kayit_id"].apply(lambda k: f"#{k}"),
        "İşlem": f["islem"].apply(lambda i: f"{ISLEM_IKON.get(i, '')} {ISLEM.get(i, i)}"),
        "Değişen Alanlar": f["degisen_alanlar"].apply(
            lambda a: ", ".join(a[:4]) + (f" +{len(a) - 4}" if a and len(a) > 4 else "")
            if a else "—"),
    })
    ui.tablo(t, anahtar="denetim", indir="denetim-izi", yukseklik=400)

    st.markdown("---")
    st.markdown("##### Kayıt Detayı")
    secenekler = {int(r.id): f"{ui.tarih_saat(r.tarih)} · {r.tablo} #{r.kayit_id} · "
                             f"{ISLEM.get(r.islem, r.islem)}" for r in f.head(120).itertuples()}
    secili = ui.secim_kutusu("Kayıt seçin", secenekler, "dn_secim", bos="— Kayıt seçin —")
    if not secili:
        return

    d = db.tek("denetim_izi", filtreler=[("id", "eq", int(secili))])
    if not d:
        return
    eski = d.get("eski_deger") or {}
    yeni = d.get("yeni_deger") or {}
    alanlar = d.get("degisen_alanlar") or sorted(set(eski) | set(yeni))
    satirlar = []
    for a in alanlar:
        e, y = eski.get(a), yeni.get(a)
        if json.dumps(e, default=str) == json.dumps(y, default=str):
            continue
        satirlar.append({"Alan": a, "Eski Değer": str(e)[:120], "Yeni Değer": str(y)[:120]})
    if satirlar:
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")
    else:
        st.caption("Alan farkı yok.")
