"""Mal kabul — parti ve SKT girişi zorunlu."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Mal Kabul", "parti ve SKT girişi")
    ui.kural_notu(
        "📥 Mal kabulde <b>parti no ve SKT girişi zorunludur</b> (FR-2.01). SKT boş bırakılırsa "
        "üretim tarihi + ürünün raf ömründen otomatik hesaplanır."
    )

    if auth.yetkili("depo"):
        if st.button("＋ Yeni Mal Kabul", type="primary"):
            st.session_state["mk_form"] = True
        if st.session_state.get("mk_form"):
            _form()

    df = db.sorgu(
        "mal_kabuller",
        select="*, cariler(unvan), depolar(ad), satin_alma_siparisleri(siparis_no), "
               "ithalat_dosyalari(dosya_no)",
        sira="tarih", tersine=True, limit=300,
    )
    if df.empty:
        st.info("Mal kabul kaydı yok.")
        return

    t = pd.DataFrame({
        "Kabul No": df["kabul_no"],
        "Tarih": df["tarih"].apply(ui.tarih_saat),
        "Tedarikçi": df["cariler"].apply(lambda x: (x or {}).get("unvan")),
        "Referans": df.apply(
            lambda r: (r["satin_alma_siparisleri"] or {}).get("siparis_no")
            or (r["ithalat_dosyalari"] or {}).get("dosya_no") or "—", axis=1),
        "Depo": df["depolar"].apply(lambda x: (x or {}).get("ad")),
        "Karantina": df["karantinaya_al"].apply(lambda x: "🟡 Evet" if x else "—"),
        "Durum": df["durum"].apply(ui.durum_etiket),
    })
    ui.tablo(t, anahtar="mk", indir="mal-kabul", yukseklik=330)

    st.markdown("---")
    secenekler = {int(r.id): f"{r.kabul_no} — {ui.tarih_bicim(r.tarih)}" for r in df.itertuples()}
    secili = ui.secim_kutusu("Kabul detayı", secenekler, "mk_secim", bos="— Kabul seçin —")
    if secili:
        _detay(int(secili))


def _detay(kabul_id: int) -> None:
    k = db.tek("mal_kabuller", select="*, cariler(unvan), depolar(ad)",
               filtreler=[("id", "eq", kabul_id)])
    s = db.sorgu("mal_kabul_satirlar",
                 select="*, urunler(sku,ad), partiler(parti_no,skt,durum), lokasyonlar(kod)",
                 filtreler=[("kabul_id", "eq", kabul_id)])
    if not k:
        return
    st.write(f"**{k['kabul_no']}** · {ui.tarih_saat(k['tarih'])} · "
             f"{(k.get('cariler') or {}).get('unvan') or '—'} · "
             f"{(k.get('depolar') or {}).get('ad') or '—'} · {ui.durum_etiket(k['durum'])}")
    if s.empty:
        st.info("Satır yok.")
        return
    st.dataframe(pd.DataFrame({
        "SKU": s["urunler"].apply(lambda x: (x or {}).get("sku")),
        "Ürün": s["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 36),
        "Parti": s.apply(lambda r: (r["partiler"] or {}).get("parti_no") or r["parti_no"] or "—", axis=1),
        "SKT": s.apply(lambda r: ui.tarih_bicim(r["skt"] or (r["partiler"] or {}).get("skt")), axis=1),
        "Miktar": s["miktar"],
        "Hasarlı": s["hasarli_miktar"],
        "Lokasyon": s["lokasyonlar"].apply(lambda x: (x or {}).get("kod")),
    }), hide_index=True, width="stretch")


@st.dialog("Yeni Mal Kabul", width="large")
def _form() -> None:
    urunler = db.sorgu("urunler", select="id,sku,ad,raf_omru_ay,alis_fiyati",
                       filtreler=[("durum", "eq", "aktif")], sira="sku")
    if urunler.empty:
        st.error("Katalogda aktif ürün yok.")
        return
    sa = db.sorgu("satin_alma_siparisleri", select="id,siparis_no,tedarikci_id",
                  filtreler=[("durum", "in", "(onaylandi,kismen_teslim)")], sira="siparis_no")
    ith = db.sorgu("ithalat_dosyalari", select="id,dosya_no",
                   filtreler=[("durum", "in", "(yolda,gumrukte,gumrukten_cekildi)")], sira="dosya_no")

    c1, c2, c3 = st.columns(3)
    with c1:
        depo_id = ui.secim_kutusu("Depo *", db.ref_secim("depo"), "mk_depo", bos=None)
    with c2:
        ted_id = ui.secim_kutusu("Tedarikçi", db.ref_secim("tedarikci", "unvan"), "mk_ted")
    with c3:
        irsaliye = st.text_input("İrsaliye No")

    c1, c2 = st.columns(2)
    with c1:
        sa_id = ui.secim_kutusu(
            "Satın Alma Siparişi",
            {int(r.id): r.siparis_no for r in sa.itertuples()} if not sa.empty else {},
            "mk_sa", bos="— Siparişsiz kabul —")
    with c2:
        ith_id = ui.secim_kutusu(
            "İthalat Dosyası",
            {int(r.id): r.dosya_no for r in ith.itertuples()} if not ith.empty else {},
            "mk_ith", bos="— Yok —")
    karantina = st.checkbox("Karantinaya al (kalite kontrol sonrası açılacak)")

    st.markdown("###### Kabul Satırları")
    if "mk_satirlar" not in st.session_state or st.session_state.get("mk_sa_onceki") != sa_id:
        st.session_state["mk_sa_onceki"] = sa_id
        if sa_id:
            sat = db.sorgu("satin_alma_satirlar",
                           select="urun_id,adet,teslim_alinan,birim_fiyat",
                           filtreler=[("siparis_id", "eq", sa_id)])
            kalanlar = []
            for r in sat.itertuples():
                kalan = float(r.adet) - float(r.teslim_alinan or 0)
                if kalan > 0:
                    u = urunler[urunler["id"] == r.urun_id]
                    kalanlar.append({
                        "Ürün": f"{u.iloc[0]['sku']} — {u.iloc[0]['ad']}" if not u.empty else "",
                        "Parti No": "", "Üretim Tarihi": None, "SKT": None,
                        "Miktar": kalan, "Hasarlı": 0.0,
                        "Birim Maliyet": float(r.birim_fiyat or 0), "Lokasyon": "otomatik",
                    })
            st.session_state["mk_satirlar"] = pd.DataFrame(kalanlar) if kalanlar else _bos_satir()
        else:
            st.session_state["mk_satirlar"] = _bos_satir()

    urun_secenek = [f"{r.sku} — {r.ad}" for r in urunler.itertuples()]
    lok_df = [l for l in db.ref()["lokasyon"]
              if l["tip"] in ("ana_depo", "mal_kabul", "karantina")]
    lok_secenek = ["otomatik"] + [l["kod"] for l in lok_df]

    duzenlenen = st.data_editor(
        st.session_state["mk_satirlar"], num_rows="dynamic", width="stretch", key="mk_editor",
        column_config={
            "Ürün": st.column_config.SelectboxColumn("Ürün *", options=urun_secenek, width="large"),
            "Parti No": st.column_config.TextColumn("Parti No", help="Boş bırakılırsa otomatik üretilir"),
            "Üretim Tarihi": st.column_config.DateColumn("Üretim Tarihi", format="DD.MM.YYYY"),
            "SKT": st.column_config.DateColumn("SKT *", format="DD.MM.YYYY"),
            "Miktar": st.column_config.NumberColumn("Miktar *", min_value=0.0, step=1.0),
            "Hasarlı": st.column_config.NumberColumn("Hasarlı", min_value=0.0, step=1.0),
            "Birim Maliyet": st.column_config.NumberColumn("Birim Maliyet", step=0.01),
            "Lokasyon": st.column_config.SelectboxColumn("Lokasyon", options=lok_secenek),
        },
    )

    c1, c2 = st.columns([1, 3])
    if c1.button("Vazgeç"):
        st.session_state.pop("mk_form", None)
        st.session_state.pop("mk_satirlar", None)
        st.rerun()
    if c2.button("Kaydet ve Stoğa Al", type="primary"):
        _kaydet(duzenlenen, urunler, depo_id, ted_id, sa_id, ith_id, irsaliye, karantina, lok_df)


def _bos_satir() -> pd.DataFrame:
    return pd.DataFrame([{
        "Ürün": None, "Parti No": "", "Üretim Tarihi": None, "SKT": None,
        "Miktar": 1.0, "Hasarlı": 0.0, "Birim Maliyet": 0.0, "Lokasyon": "otomatik",
    }])


def _kaydet(df, urunler, depo_id, ted_id, sa_id, ith_id, irsaliye, karantina, lok_df) -> None:
    df = df[df["Ürün"].notna() & (df["Ürün"] != "")]
    if df.empty:
        st.error("En az bir kabul satırı ekleyin.")
        return
    if not depo_id:
        st.error("Depo seçilmelidir.")
        return

    sku_map = {f"{r.sku} — {r.ad}": int(r.id) for r in urunler.itertuples()}
    lok_map = {l["kod"]: l["id"] for l in lok_df}
    satirlar = []
    for _, r in df.iterrows():
        uid = sku_map.get(r["Ürün"])
        if not uid:
            st.error(f"Ürün tanınmadı: {r['Ürün']}")
            return
        miktar = float(r.get("Miktar") or 0)
        if miktar <= 0:
            st.error("Miktar sıfırdan büyük olmalıdır.")
            return
        skt = r.get("SKT")
        uretim = r.get("Üretim Tarihi")
        if (skt is None or pd.isna(skt)) and (uretim is None or pd.isna(uretim)):
            st.error(f"{r['Ürün']}: SKT veya üretim tarihi girilmelidir (FR-2.01).")
            return
        lok = r.get("Lokasyon")
        satirlar.append({
            "urun_id": uid,
            "parti_no": (str(r.get("Parti No") or "").strip() or None),
            "uretim_tarihi": None if (uretim is None or pd.isna(uretim)) else str(uretim),
            "skt": None if (skt is None or pd.isna(skt)) else str(skt),
            "miktar": miktar,
            "hasarli_miktar": float(r.get("Hasarlı") or 0),
            "birim_maliyet": float(r.get("Birim Maliyet") or 0) or None,
            "lokasyon_id": lok_map.get(lok) if lok and lok != "otomatik" else None,
        })

    import random
    import string

    kabul_no = "MK-" + date.today().strftime("%y%m%d") + "-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=4))
    try:
        kabul = db.ekle("mal_kabuller", {
            "kabul_no": kabul_no, "depo_id": depo_id, "tedarikci_id": ted_id,
            "satin_alma_id": sa_id, "ithalat_dosya_id": ith_id,
            "irsaliye_no": irsaliye or None, "karantinaya_al": karantina,
            "olusturan": db.kullanici_id(),
        })
        kid = kabul[0]["id"]
        db.ekle("mal_kabul_satirlar", [{**s, "kabul_id": kid} for s in satirlar])
        sonuc = db.rpc("mal_kabul_tamamla", {"p_kabul_id": kid})
        st.success(f"Mal kabul tamamlandı: {kabul_no} · {sonuc.get('satir')} satır stoğa alındı.")
        st.session_state.pop("mk_form", None)
        st.session_state.pop("mk_satirlar", None)
        st.rerun()
    except Exception as e:
        st.error(f"Kaydedilemedi: {e}")
