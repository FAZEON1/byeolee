"""Sayım — tam ve çevrimsel; fark onayı olmadan stoğa işlenmez (BR-10)."""
from __future__ import annotations

import random
import string
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Sayım", "çevrimsel ve tam sayım")
    ui.kural_notu(
        "☑️ <b>Sayım farkı, yetkili onayı olmadan stoğa işlenmez (BR-10).</b> "
        "Onaydan sonra fark, stok hareketi olarak kalıcı biçimde kaydedilir."
    )

    if auth.yetkili("depo") and st.button("＋ Yeni Sayım Başlat", type="primary"):
        _yeni()

    df = db.sorgu("sayimlar", select="*, depolar(ad)", sira="baslangic", tersine=True)
    if df.empty:
        st.info("Sayım kaydı yok.")
        return

    ui.tablo(pd.DataFrame({
        "Sayım No": df["sayim_no"],
        "Başlangıç": df["baslangic"].apply(ui.tarih_saat),
        "Tip": df["tip"].apply(lambda t: "Tam Sayım" if t == "tam" else "Kısmi"),
        "Depo": df["depolar"].apply(lambda x: (x or {}).get("ad")),
        "Durum": df["durum"].apply(ui.durum_etiket),
        "Onay": df["onay_tarihi"].apply(ui.tarih_saat),
    }), anahtar="sayim", yukseklik=250)

    st.markdown("---")
    secenekler = {int(r.id): f"{r.sayim_no} — {ui.DURUM_AD.get(r.durum, r.durum)}"
                  for r in df.itertuples()}
    secili = ui.secim_kutusu("Sayım detayı", secenekler, "sy_secim", bos="— Sayım seçin —")
    if secili:
        _detay(int(secili))


@st.dialog("Yeni Sayım Başlat")
def _yeni() -> None:
    depo_id = ui.secim_kutusu("Depo *", db.ref_secim("depo"), "sy_depo", bos=None)
    tip = st.selectbox("Sayım tipi", ["kismi", "tam"],
                       format_func=lambda t: "Kısmi (çevrimsel)" if t == "kismi" else "Tam sayım")
    kriter = "hepsi"
    kategori_id = None
    if tip == "kismi":
        kriter = st.selectbox(
            "Kısmi sayım kriteri", ["hepsi", "skt90", "kategori"],
            format_func=lambda k: {"hepsi": "Depodaki tüm stok",
                                   "skt90": "SKT'sine 90 günden az kalanlar",
                                   "kategori": "Belirli kategori"}[k])
        if kriter == "kategori":
            kategori_id = ui.secim_kutusu("Kategori", db.ref_secim("kategori"), "sy_kat", bos=None)
    not_ = st.text_input("Not")

    if st.button("Sayımı Başlat", type="primary"):
        if not depo_id:
            st.error("Depo seçilmelidir.")
            return
        stoklar = db.sorgu("stok", select="*, partiler(skt,birim_maliyet), urunler(kategori_id)",
                           filtreler=[("depo_id", "eq", depo_id), ("fiziksel_miktar", "gt", 0)])
        if not stoklar.empty and kriter == "skt90":
            sinir = str(date.today() + timedelta(days=90))
            stoklar = stoklar[stoklar["partiler"].apply(
                lambda p: bool((p or {}).get("skt")) and (p or {}).get("skt") <= sinir)]
        if not stoklar.empty and kriter == "kategori" and kategori_id:
            stoklar = stoklar[stoklar["urunler"].apply(
                lambda u: (u or {}).get("kategori_id") == kategori_id)]
        if stoklar.empty:
            st.error("Bu kritere uyan stok bulunamadı.")
            return

        no = "SYM-" + date.today().strftime("%y%m%d") + "-" + "".join(
            random.choices(string.ascii_uppercase, k=3))
        try:
            sy = db.ekle("sayimlar", {
                "sayim_no": no, "depo_id": depo_id, "tip": tip, "durum": "sayiliyor",
                "notlar": not_ or None, "kriter": {"kriter": kriter, "kategori": kategori_id},
                "olusturan": db.kullanici_id(),
            })[0]
            db.ekle("sayim_satirlar", [{
                "sayim_id": sy["id"], "urun_id": int(r.urun_id), "parti_id": int(r.parti_id),
                "lokasyon_id": int(r.lokasyon_id), "sistem_miktar": float(r.fiziksel_miktar),
                "birim_maliyet": float((r.partiler or {}).get("birim_maliyet") or 0),
            } for r in stoklar.itertuples()])
            st.success(f"Sayım başlatıldı: {no} · {len(stoklar)} satır")
            st.rerun()
        except Exception as e:
            st.error(f"Başlatılamadı: {e}")


def _detay(sayim_id: int) -> None:
    sy = db.tek("sayimlar", select="*, depolar(ad)", filtreler=[("id", "eq", sayim_id)])
    sat = db.sorgu("sayim_satirlar",
                   select="*, urunler(sku,ad), partiler(parti_no,skt), lokasyonlar(kod)",
                   filtreler=[("sayim_id", "eq", sayim_id)], sira="id")
    if not sy or sat.empty:
        st.info("Sayım satırı yok.")
        return
    M = auth.maliyet_gorur()
    acik = sy["durum"] not in ("tamamlandi", "iptal")

    sayilan = sat[sat["sayilan_miktar"].notna()]
    farkli = sayilan[sayilan["fark"] != 0]
    fark_tutar = float((farkli["fark"] * farkli["birim_maliyet"].fillna(0)).sum()) if not farkli.empty else 0.0

    kartlar = [
        {"baslik": "Toplam Satır", "deger": str(len(sat)), "alt": "", "renk": "lacivert"},
        {"baslik": "Sayılan", "deger": str(len(sayilan)), "alt": "", "renk": "yesil"},
        {"baslik": "Farklı", "deger": str(len(farkli)), "alt": "",
         "renk": "turuncu" if len(farkli) else "gri"},
    ]
    if M:
        kartlar.append({"baslik": "Fark Tutarı", "deger": ui.para0(fark_tutar), "alt": "",
                        "renk": "kirmizi" if fark_tutar < 0 else "gri"})
    ui.kpi_satiri(kartlar, sutun=4)

    t = pd.DataFrame({
        "id": sat["id"],
        "SKU": sat["urunler"].apply(lambda x: (x or {}).get("sku")),
        "Ürün": sat["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 30),
        "Parti": sat["partiler"].apply(lambda x: (x or {}).get("parti_no")),
        "Lokasyon": sat["lokasyonlar"].apply(lambda x: (x or {}).get("kod")),
        "Sistem": sat["sistem_miktar"],
        "Sayılan": sat["sayilan_miktar"],
        "Fark": sat["fark"],
    })

    if acik:
        st.caption("Sayılan miktarları girip **Sayımı Kaydet**'e basın.")
        duzenlenen = st.data_editor(
            t, width="stretch", hide_index=True, key=f"sy_ed_{sayim_id}",
            disabled=["id", "SKU", "Ürün", "Parti", "Lokasyon", "Sistem", "Fark"],
            column_config={"id": None,
                           "Sistem": ui.sayi_kolonu("Sistem", 2),
                           "Sayılan": st.column_config.NumberColumn("Sayılan", step=1.0),
                           "Fark": ui.sayi_kolonu("Fark", 2)},
        )
        c1, c2 = st.columns([1, 3])
        if c1.button("💾 Sayımı Kaydet", key=f"sy_kaydet_{sayim_id}"):
            _sayim_kaydet(duzenlenen, t)
        if auth.yetkili("onay") and c2.button(
                "✓ Farkları Onayla ve Stoğa İşle", type="primary", key=f"sy_onay_{sayim_id}"):
            _onayla(sayim_id, len(farkli), fark_tutar)
    else:
        st.dataframe(t.drop(columns=["id"]), hide_index=True, width="stretch")


def _sayim_kaydet(yeni: pd.DataFrame, eski: pd.DataFrame) -> None:
    from datetime import datetime, timezone
    degisen = 0
    for _, satir in yeni.iterrows():
        onceki = eski[eski["id"] == satir["id"]]["Sayılan"].iloc[0]
        if pd.isna(satir["Sayılan"]) and pd.isna(onceki):
            continue
        if satir["Sayılan"] != onceki:
            db.guncelle("sayim_satirlar", {
                "sayilan_miktar": None if pd.isna(satir["Sayılan"]) else float(satir["Sayılan"]),
                "sayan": db.kullanici_id(),
                "sayim_zamani": datetime.now(timezone.utc).isoformat(),
            }, [("id", "eq", int(satir["id"]))])
            degisen += 1
    st.success(f"{degisen} satır kaydedildi.")
    st.rerun()


@st.dialog("Sayım Onayı")
def _onayla(sayim_id: int, fark_adet: int, fark_tutar: float) -> None:
    st.warning(f"**{fark_adet} satırda fark var.** Onayladığınızda bu farklar stok hareketi "
               f"olarak kalıcı biçimde kaydedilecek ve geri alınamayacak.", icon="⚠️")
    if auth.maliyet_gorur():
        st.write(f"Toplam fark tutarı: **{ui.para(fark_tutar)}**")
    if st.button("Onayla ve İşle", type="primary"):
        try:
            sonuc = db.rpc("sayim_onayla", {"p_sayim_id": sayim_id})
            st.success(f"Sayım onaylandı · {sonuc.get('duzeltilen_satir')} satır düzeltildi · "
                       f"fark {ui.para(sonuc.get('fark_tutari'))}")
            st.rerun()
        except Exception as e:
            st.error(f"Onaylanamadı: {e}")
