"""Satın alma siparişleri ve onay akışı."""
from __future__ import annotations

import random
import string
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Satın Alma", "sipariş ve onay")

    if auth.yetkili("satinalma") and st.button("＋ Yeni Sipariş", type="primary"):
        st.session_state["sa_form"] = True
    if st.session_state.get("sa_form"):
        _form()

    df = db.sorgu("satin_alma_siparisleri", select="*, cariler(unvan,ulke,teslim_sekli)",
                  sira="siparis_tarihi", tersine=True)
    if df.empty:
        st.info("Satın alma siparişi yok.")
        return

    bugun = pd.Timestamp.today().normalize()
    eta = pd.to_datetime(df["eta"], errors="coerce")
    gecikme = ((bugun - eta).dt.days).where(df["durum"].isin(["onaylandi", "kismen_teslim"]))

    ui.tablo(pd.DataFrame({
        "Sipariş No": df["siparis_no"],
        "Tedarikçi": df["cariler"].apply(lambda x: (x or {}).get("unvan")),
        "Tarih": df["siparis_tarihi"].apply(ui.tarih_bicim),
        "ETA": df["eta"].apply(ui.tarih_bicim),
        "Gecikme": gecikme.apply(lambda g: f"⚠️ {int(g)} gün" if pd.notna(g) and g > 0 else "—"),
        "Tutar": df["genel_toplam"],
        "Döviz": df["para_birimi"],
        "Durum": df["durum"].apply(ui.durum_etiket),
    }), anahtar="sa", indir="satin-alma", yukseklik=330,
        kolonlar={"Tutar": ui.sayi_kolonu("Tutar", 2)})

    st.markdown("---")
    secenekler = {int(r.id): f"{r.siparis_no} — {(r.cariler or {}).get('unvan','')}"
                  for r in df.itertuples()}
    secili = ui.secim_kutusu("Sipariş detayı", secenekler, "sa_secim", bos="— Sipariş seçin —")
    if secili:
        _detay(int(secili))


def _detay(siparis_id: int) -> None:
    s = db.tek("satin_alma_siparisleri", select="*, cariler(unvan,ulke)",
               filtreler=[("id", "eq", siparis_id)])
    sat = db.sorgu("satin_alma_satirlar", select="*, urunler(sku,ad)",
                   filtreler=[("siparis_id", "eq", siparis_id)])
    if not s:
        return

    limit = float(db.ayar("sa_onay_limiti", 50000) or 50000)
    tutar_try = float(s.get("genel_toplam") or 0) * float(s.get("kur") or 1)
    if s["durum"] == "taslak" and tutar_try > limit:
        st.warning(f"Bu sipariş {ui.para0(limit)} onay limitinin üzerinde — "
                   "yönetici onayı gerekiyor (BR-11).", icon="⚠️")

    bilgi = {
        "Tedarikçi": f"{(s.get('cariler') or {}).get('unvan','—')} "
                     f"({(s.get('cariler') or {}).get('ulke','')})",
        "Sipariş Tarihi": ui.tarih_bicim(s["siparis_tarihi"]),
        "Tahmini Varış (ETA)": ui.tarih_bicim(s.get("eta")),
        "Teslim Şekli": s.get("teslim_sekli") or "—",
        "Para Birimi / Kur": f"{s['para_birimi']} × {ui.sayi_bicim(s.get('kur'), 2)}",
        "Durum": ui.durum_etiket(s["durum"]),
        "Not": s.get("notlar") or "—",
    }
    st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                 hide_index=True, width="stretch")

    if not sat.empty:
        st.dataframe(pd.DataFrame({
            "SKU": sat["urunler"].apply(lambda x: (x or {}).get("sku")),
            "Ürün": sat["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 38),
            "Sipariş": sat["adet"],
            "Teslim": sat["teslim_alinan"],
            "Kalan": sat["adet"] - sat["teslim_alinan"].fillna(0),
            "Birim Fiyat": sat["birim_fiyat"],
            "Tutar": sat["satir_toplam"],
        }), hide_index=True, width="stretch", column_config={
            "Sipariş": ui.sayi_kolonu("Sipariş", 0),
            "Teslim": ui.sayi_kolonu("Teslim", 0),
            "Kalan": ui.sayi_kolonu("Kalan", 0),
            "Birim Fiyat": ui.sayi_kolonu("Birim Fiyat", 2),
            "Tutar": ui.sayi_kolonu("Tutar", 2),
        })

    if auth.yetkili("satinalma") and s["durum"] == "taslak":
        if st.button("✓ Siparişi Onayla", type="primary", key="sa_onayla"):
            if tutar_try > limit and not auth.yetkili("sistem"):
                st.error(f"{ui.para0(limit)} üzeri siparişler yönetici onayı gerektirir (BR-11).")
            else:
                db.guncelle("satin_alma_siparisleri", {
                    "durum": "onaylandi", "onaylayan": db.kullanici_id(),
                    "onay_tarihi": datetime.now(timezone.utc).isoformat(),
                }, [("id", "eq", siparis_id)])
                st.success("Sipariş onaylandı.")
                st.rerun()


@st.dialog("Yeni Satın Alma Siparişi", width="large")
def _form() -> None:
    urunler = db.sorgu("urunler", select="id,sku,ad,alis_fiyati",
                       filtreler=[("durum", "eq", "aktif")], sira="sku")
    c1, c2 = st.columns(2)
    with c1:
        ted_id = ui.secim_kutusu("Tedarikçi *", db.ref_secim("tedarikci", "unvan"),
                                 "sa_ted", bos=None)
        tarih = st.date_input("Sipariş Tarihi", value=date.today(), format="DD.MM.YYYY")
        pb = st.selectbox("Para Birimi", ["USD", "EUR", "TRY", "GBP"])
    with c2:
        eta = st.date_input("ETA", value=date.today() + timedelta(days=45), format="DD.MM.YYYY")
        teslim = st.selectbox("Teslim Şekli", ["FOB", "CIF", "EXW", "DDP", "DAP"])
        kur = st.number_input("Kur", value=48.50, step=0.01)
    not_ = st.text_input("Not")

    st.markdown("###### Sipariş Satırları")
    if "sa_satirlar" not in st.session_state:
        st.session_state["sa_satirlar"] = pd.DataFrame(
            [{"Ürün": None, "Adet": 1.0, "Birim Fiyat": 0.0}])
    urun_secenek = [f"{r.sku} — {r.ad}" for r in urunler.itertuples()]
    duzenlenen = st.data_editor(
        st.session_state["sa_satirlar"], num_rows="dynamic", width="stretch", key="sa_editor",
        column_config={
            "Ürün": st.column_config.SelectboxColumn("Ürün *", options=urun_secenek, width="large"),
            "Adet": st.column_config.NumberColumn("Adet *", min_value=0.0, step=1.0),
            "Birim Fiyat": st.column_config.NumberColumn("Birim Fiyat", step=0.01),
        })
    toplam = float((duzenlenen["Adet"].fillna(0) * duzenlenen["Birim Fiyat"].fillna(0)).sum())
    st.write(f"**Toplam:** {ui.sayi_bicim(toplam, 2)} {pb}")

    c1, c2 = st.columns([1, 3])
    if c1.button("Vazgeç"):
        st.session_state.pop("sa_form", None)
        st.session_state.pop("sa_satirlar", None)
        st.rerun()
    if c2.button("Taslak Olarak Kaydet", type="primary"):
        df = duzenlenen[duzenlenen["Ürün"].notna()]
        if not ted_id or df.empty:
            st.error("Tedarikçi ve en az bir satır gerekli.")
            return
        sku_map = {f"{r.sku} — {r.ad}": int(r.id) for r in urunler.itertuples()}
        no = f"SA-{date.today().year}-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=4))
        try:
            sp = db.ekle("satin_alma_siparisleri", {
                "siparis_no": no, "tedarikci_id": ted_id, "siparis_tarihi": str(tarih),
                "eta": str(eta), "para_birimi": pb, "kur": kur, "teslim_sekli": teslim,
                "notlar": not_ or None, "ara_toplam": toplam, "genel_toplam": toplam,
                "olusturan": db.kullanici_id(),
            })[0]
            db.ekle("satin_alma_satirlar", [{
                "siparis_id": sp["id"], "urun_id": sku_map[r.Ürün],
                "adet": float(r.Adet or 0), "birim_fiyat": float(r._asdict()["Birim Fiyat"] or 0),
            } for r in df.itertuples()])
            st.success(f"Sipariş oluşturuldu: {no}")
            st.session_state.pop("sa_form", None)
            st.session_state.pop("sa_satirlar", None)
            st.rerun()
        except Exception as e:
            st.error(f"Kaydedilemedi: {e}")
