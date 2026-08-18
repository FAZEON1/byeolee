"""Toplama listesi ve sevkiyat — FEFO sırasına göre rafa göre sıralı."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from modules import siparisler as sip_mod


def goster() -> None:
    ui.baslik("Toplama & Sevkiyat", "FEFO toplama listesi")

    sip = db.sorgu("satis_siparisleri", select="*, kanallar(ad)",
                   filtreler=[("durum", "in", "(stok_rezerve,toplamada,paketlendi)")],
                   sira="siparis_tarihi")
    if sip.empty:
        st.success("Sevk bekleyen sipariş yok 👍")
        return

    ids = ",".join(str(int(i)) for i in sip["id"])
    pdet = db.sorgu(
        "sevk_parti_detay",
        select="*, partiler(parti_no,skt), lokasyonlar(kod), "
               "satis_satirlar(urun_id, urunler(sku,ad))",
        filtreler=[("siparis_id", "in", f"({ids})"), ("sevk_tarihi", "is", "null")],
    )

    sip_no = {int(r.id): r.siparis_no for r in sip.itertuples()}
    if pdet.empty:
        toplama = pd.DataFrame()
    else:
        toplama = pd.DataFrame({
            "Raf": pdet["lokasyonlar"].apply(lambda x: (x or {}).get("kod")),
            "SKU": pdet["satis_satirlar"].apply(
                lambda x: ((x or {}).get("urunler") or {}).get("sku")),
            "Ürün": pdet["satis_satirlar"].apply(
                lambda x: ((x or {}).get("urunler") or {}).get("ad") or "").str.slice(0, 36),
            "Parti (FEFO)": pdet["partiler"].apply(lambda x: (x or {}).get("parti_no")),
            "SKT": pdet["partiler"].apply(lambda x: ui.tarih_bicim((x or {}).get("skt"))),
            "Adet": pdet["miktar"],
            "Sipariş": pdet["siparis_id"].map(sip_no),
        }).sort_values(["Raf", "SKU"])

    ui.kpi_satiri([
        {"baslik": "Sevke Hazır Sipariş", "deger": str(len(sip)), "alt": "", "renk": "lacivert"},
        {"baslik": "Toplanacak Kalem", "deger": str(len(toplama)), "alt": "", "renk": "lacivert"},
        {"baslik": "Toplam Adet",
         "deger": ui.sayi_bicim(toplama["Adet"].sum() if not toplama.empty else 0),
         "alt": "", "renk": "yesil"},
        {"baslik": "Farklı Raf",
         "deger": str(toplama["Raf"].nunique() if not toplama.empty else 0),
         "alt": "", "renk": "gri"},
    ], sutun=4)

    sol, sag = st.columns([2, 1], gap="medium")
    with sol:
        st.markdown("##### Toplama Listesi (rafa göre sıralı)")
        ui.tablo(toplama, anahtar="topl", indir="toplama-listesi", yukseklik=430,
                 kolonlar={"Adet": ui.sayi_kolonu("Adet")})
    with sag:
        st.markdown("##### Sevk Bekleyen Siparişler")
        for r in sip.itertuples():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(
                    f"**{r.siparis_no}**  \n"
                    f"<span style='font-size:.8rem;color:#64748b'>{r.musteri_adi or ''} · "
                    f"{(r.kanallar or {}).get('ad', '')} · {ui.para0(r.genel_toplam)}</span>",
                    unsafe_allow_html=True)
                if c2.button("Sevk", key=f"sv_{r.id}", type="primary"):
                    sip_mod.sevk_dialog(int(r.id), r._asdict())
