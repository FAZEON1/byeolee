"""İade yönetimi — hijyen ve kalite kontrolü (BR-09)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from lib import auth, db, ui

SEBEP = {
    "hasarli": "Hasarlı geldi", "yanlis_urun": "Yanlış ürün", "vazgecti": "Müşteri vazgeçti",
    "skt_yakin": "SKT yakın", "alerjik": "Alerjik reaksiyon", "kalite": "Kalite şikâyeti",
}


def goster() -> None:
    ui.baslik("İadeler", "hijyen ve kalite kontrolü")
    ui.kural_notu(
        "🧴 <b>Ambalajı açılmış kozmetik ürün yeniden satılabilir stoğa alınamaz (BR-09).</b> "
        "Sistem bu kararı teknik olarak engeller — hasarlı veya imha seçilmelidir."
    )

    if auth.yetkili("satis") and st.button("＋ Yeni İade Kaydı", type="primary"):
        _form()

    df = db.sorgu("iadeler",
                  select="*, satis_siparisleri(siparis_no,musteri_adi), kanallar(ad)",
                  sira="tarih", tersine=True, limit=400)
    if df.empty:
        st.info("İade kaydı yok.")
        return

    ui.tablo(pd.DataFrame({
        "İade No": df["iade_no"],
        "Tarih": df["tarih"].apply(ui.tarih_saat),
        "Sipariş": df["satis_siparisleri"].apply(lambda x: (x or {}).get("siparis_no") or "—"),
        "Kanal": df["kanallar"].apply(lambda x: (x or {}).get("ad")),
        "Sebep": df["sebep"].map(SEBEP).fillna(df["sebep"]),
        "Ambalaj": df["ambalaj_acik"].apply(lambda x: "🟠 Açılmış" if x else "🟢 Kapalı"),
        "Karar": df["karar"].apply(ui.durum_etiket),
    }), anahtar="iade", indir="iadeler", yukseklik=330)

    st.markdown("---")
    secenekler = {int(r.id): f"{r.iade_no} — {SEBEP.get(r.sebep, r.sebep)} — "
                             f"{ui.DURUM_AD.get(r.karar, r.karar)}" for r in df.itertuples()}
    secili = ui.secim_kutusu("İade detayı", secenekler, "ia_secim", bos="— İade seçin —")
    if secili:
        _detay(int(secili))


def _detay(iade_id: int) -> None:
    i = db.tek("iadeler", select="*, satis_siparisleri(siparis_no,musteri_adi), kanallar(ad)",
               filtreler=[("id", "eq", iade_id)])
    sat = db.sorgu("iade_satirlar", select="*, urunler(sku,ad), partiler(parti_no,skt)",
                   filtreler=[("iade_id", "eq", iade_id)])
    if not i:
        return
    if i.get("ambalaj_acik"):
        st.warning("**Ambalaj açılmış.** Hijyen gereği yeniden satılabilir stoğa alınamaz (BR-09).",
                   icon="🧴")

    bilgi = {
        "Sipariş": (i.get("satis_siparisleri") or {}).get("siparis_no") or "—",
        "Müşteri": (i.get("satis_siparisleri") or {}).get("musteri_adi") or "—",
        "Kanal": (i.get("kanallar") or {}).get("ad") or "—",
        "Tarih": ui.tarih_saat(i["tarih"]),
        "Sebep": SEBEP.get(i["sebep"], i["sebep"]),
        "Ambalaj": "Açılmış" if i.get("ambalaj_acik") else "Kapalı",
        "Karar": ui.durum_etiket(i["karar"]),
        "Not": i.get("notlar") or "—",
    }
    st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                 hide_index=True, width="stretch")

    if not sat.empty:
        st.dataframe(pd.DataFrame({
            "SKU": sat["urunler"].apply(lambda x: (x or {}).get("sku")),
            "Ürün": sat["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 36),
            "Parti": sat["partiler"].apply(lambda x: (x or {}).get("parti_no") or "—"),
            "Adet": sat["miktar"],
            "Karar": sat["karar"].apply(ui.durum_etiket),
        }), hide_index=True, width="stretch")

    if auth.yetkili("satis") and i["karar"] == "bekliyor":
        st.markdown("###### Kalite Kararı")
        c1, c2, c3 = st.columns(3)
        if not i.get("ambalaj_acik"):
            if c1.button("✓ Yeniden Satılabilir", type="primary", key=f"ik1_{iade_id}",
                         use_container_width=True):
                _karar(iade_id, "yeniden_satilabilir")
        else:
            c1.button("✓ Yeniden Satılabilir", disabled=True, key=f"ik1d_{iade_id}",
                      help="Ambalaj açılmış — BR-09 gereği engellendi", use_container_width=True)
        if c2.button("⚠ Hasarlı", key=f"ik2_{iade_id}", use_container_width=True):
            _karar(iade_id, "hasarli")
        if c3.button("🗑 İmha", key=f"ik3_{iade_id}", use_container_width=True):
            _karar(iade_id, "imha")


def _karar(iade_id: int, karar: str) -> None:
    try:
        db.rpc("iade_karar_ver", {"p_iade_id": iade_id, "p_karar": karar})
        st.success(f"İade kararı verildi: {ui.DURUM_AD.get(karar, karar)}")
        st.rerun()
    except Exception as e:
        st.error(f"Karar verilemedi: {e}")


@st.dialog("Yeni İade Kaydı", width="large")
def _form() -> None:
    sip = db.sorgu("satis_siparisleri", select="id,siparis_no,musteri_adi,kanal_id",
                   filtreler=[("durum", "in", "(kargoya_verildi,teslim_edildi)")],
                   sira="siparis_tarihi", tersine=True, limit=200)
    if sip.empty:
        st.info("Sevk edilmiş sipariş yok.")
        return
    secenekler = {int(r.id): f"{r.siparis_no} — {r.musteri_adi or ''}" for r in sip.itertuples()}
    sip_id = ui.secim_kutusu("Sipariş *", secenekler, "ia_sip", bos="— Seçiniz —")

    c1, c2 = st.columns(2)
    sebep = c1.selectbox("İade Sebebi *", list(SEBEP), format_func=lambda s: SEBEP[s])
    kargo = c2.number_input("Kargo Maliyeti ₺", value=0.0, step=1.0)
    ambalaj = st.checkbox("Ambalaj açılmış (açıksa yeniden satılamaz)")
    not_ = st.text_input("Not")

    if not sip_id:
        return
    pdet = db.sorgu("sevk_parti_detay",
                    select="*, partiler(parti_no,skt), "
                           "satis_satirlar(urun_id,adet,birim_fiyat, urunler(sku,ad))",
                    filtreler=[("siparis_id", "eq", sip_id)])
    if pdet.empty:
        st.info("Bu siparişte sevk kaydı yok.")
        return

    st.markdown("###### İade Edilen Kalemler")
    tablo = pd.DataFrame({
        "SKU": pdet["satis_satirlar"].apply(
            lambda x: ((x or {}).get("urunler") or {}).get("sku")),
        "Ürün": pdet["satis_satirlar"].apply(
            lambda x: ((x or {}).get("urunler") or {}).get("ad") or "").str.slice(0, 30),
        "Parti": pdet["partiler"].apply(lambda x: (x or {}).get("parti_no")),
        "Sevk": pdet["miktar"],
        "İade Adedi": 0.0,
    })
    duzenlenen = st.data_editor(
        tablo, width="stretch", hide_index=True, key="ia_editor",
        disabled=["SKU", "Ürün", "Parti", "Sevk"],
        column_config={"İade Adedi": st.column_config.NumberColumn(
            "İade Adedi", min_value=0.0, step=1.0)})

    if st.button("İade Kaydet", type="primary"):
        secilen = duzenlenen[duzenlenen["İade Adedi"] > 0]
        if secilen.empty:
            st.error("En az bir ürün için iade adedi girin.")
            return
        kanal_id = int(sip[sip["id"] == sip_id]["kanal_id"].iloc[0])
        no = "IAD-" + datetime.now().strftime("%y%m%d%H%M%S")[-8:]
        try:
            iade = db.ekle("iadeler", {
                "iade_no": no, "siparis_id": sip_id, "kanal_id": kanal_id,
                "sebep": sebep, "ambalaj_acik": ambalaj, "kargo_maliyeti": kargo,
                "notlar": not_ or None, "olusturan": db.kullanici_id(),
            })[0]
            satirlar = []
            for idx, r in secilen.iterrows():
                kaynak = pdet.loc[idx]
                ss = kaynak["satis_satirlar"] or {}
                satirlar.append({
                    "iade_id": iade["id"], "urun_id": ss.get("urun_id"),
                    "parti_id": int(kaynak["parti_id"]),
                    "miktar": float(r["İade Adedi"]),
                    "birim_fiyat": float(ss.get("birim_fiyat") or 0),
                })
            db.ekle("iade_satirlar", satirlar)
            st.success(f"İade kaydedildi: {no} — kalite kararı bekliyor.")
            st.rerun()
        except Exception as e:
            st.error(f"Kaydedilemedi: {e}")
