"""Tedarikçi, müşteri ve cari hesaplar."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def tedarikciler() -> None:
    _liste("tedarikci", "Tedarikçiler")


def musteriler() -> None:
    _liste("musteri", "Müşteriler")


def _liste(tip: str, baslik: str) -> None:
    ui.baslik(baslik, "cari kartlar")
    F = auth.yetkili("finans")

    df = db.sorgu("cariler", filtreler=[("tip", "eq", tip)], sira="unvan")
    if df.empty:
        st.info("Kayıt yok.")
    else:
        bak = db.sorgu("v_cari_bakiye", filtreler=[("tip", "eq", tip)])
        if not bak.empty:
            df = df.merge(bak[["cari_id", "bakiye_try", "son_hareket"]],
                          left_on="id", right_on="cari_id", how="left")

        t = pd.DataFrame({
            "Kod": df["kod"],
            "Unvan": df["unvan"],
            "Yetkili": df["yetkili_kisi"],
            "Ülke / Şehir": df["ulke"].fillna("") + df["sehir"].apply(
                lambda s: f" / {s}" if s else ""),
            "Telefon": df["telefon"],
            "E-posta": df["eposta"],
            "Para Br.": df["para_birimi"],
            "Vade (gün)": df["odeme_vadesi_gun"],
        })
        if tip == "tedarikci":
            t["Tedarik (gün)"] = df["tedarik_suresi_gun"]
        if F and "bakiye_try" in df:
            t["Bakiye"] = df["bakiye_try"]

        ui.tablo(t, anahtar=f"cari_{tip}", indir=tip, yukseklik=330,
                 kolonlar={"Bakiye": ui.sayi_kolonu("Bakiye", 0, True)})

    if auth.yetkili("finans"):
        if st.button("＋ Yeni Kayıt", type="primary", key=f"c_yeni_{tip}"):
            _form(None, tip)

    if not df.empty:
        st.markdown("---")
        secenekler = {int(r.id): f"{r.kod or ''} {r.unvan}".strip() for r in df.itertuples()}
        secili = ui.secim_kutusu("Cari detayı", secenekler, f"c_secim_{tip}",
                                 bos="— Cari seçin —")
        if secili:
            _detay(int(secili), tip)


def _detay(cari_id: int, tip: str) -> None:
    c = db.tek("cariler", filtreler=[("id", "eq", cari_id)])
    if not c:
        return
    hrk = db.sorgu("cari_hareketler", filtreler=[("cari_id", "eq", cari_id)],
                   sira="tarih", tersine=True, limit=60)
    bilgi = {
        "Kod": c.get("kod") or "—",
        "Vergi D. / No": f"{c.get('vergi_dairesi') or '—'} / {c.get('vergi_no') or '—'}",
        "Ülke / Şehir": f"{c.get('ulke') or '—'} / {c.get('sehir') or '—'}",
        "Adres": c.get("adres") or "—",
        "Yetkili": c.get("yetkili_kisi") or "—",
        "Telefon / E-posta": f"{c.get('telefon') or '—'} · {c.get('eposta') or '—'}",
        "Para Birimi": c.get("para_birimi"),
        "Ödeme Vadesi": f"{c['odeme_vadesi_gun']} gün" if c.get("odeme_vadesi_gun") else "—",
    }
    if tip == "tedarikci":
        bilgi["Teslim Şekli"] = c.get("teslim_sekli") or "—"
        bilgi["Tedarik Süresi"] = (f"{c['tedarik_suresi_gun']} gün"
                                   if c.get("tedarik_suresi_gun") else "—")
    st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                 hide_index=True, width="stretch")

    if auth.yetkili("finans") and not hrk.empty:
        st.markdown("###### Son Hareketler")
        st.dataframe(pd.DataFrame({
            "Tarih": hrk["tarih"].apply(ui.tarih_bicim),
            "Belge": hrk["belge_tipi"].fillna("—"),
            "Açıklama": hrk["aciklama"].fillna("—"),
            "Borç": hrk.apply(lambda r: r["tutar_try"] if r["yon"] == "borc" else None, axis=1),
            "Alacak": hrk.apply(lambda r: r["tutar_try"] if r["yon"] == "alacak" else None, axis=1),
        }), hide_index=True, width="stretch", column_config={
            "Borç": ui.sayi_kolonu("Borç", 2, True),
            "Alacak": ui.sayi_kolonu("Alacak", 2, True),
        })

    if auth.yetkili("finans") and st.button("✎ Düzenle", key=f"c_duz_{cari_id}"):
        _form(cari_id, tip)


@st.dialog("Cari Kartı", width="large")
def _form(cari_id: int | None, tip: str) -> None:
    c = db.tek("cariler", filtreler=[("id", "eq", cari_id)]) if cari_id else {}
    c = c or {}
    with st.form("cari_form"):
        c1, c2 = st.columns(2)
        kod = c1.text_input("Kod", value=c.get("kod") or "")
        unvan = c2.text_input("Unvan *", value=c.get("unvan") or "")
        c1, c2, c3 = st.columns(3)
        vd = c1.text_input("Vergi Dairesi", value=c.get("vergi_dairesi") or "")
        vno = c2.text_input("Vergi / TC No", value=c.get("vergi_no") or "")
        ulke = c3.text_input("Ülke", value=c.get("ulke") or "Türkiye")
        c1, c2, c3 = st.columns(3)
        sehir = c1.text_input("Şehir", value=c.get("sehir") or "")
        yetkili = c2.text_input("Yetkili Kişi", value=c.get("yetkili_kisi") or "")
        tel = c3.text_input("Telefon", value=c.get("telefon") or "")
        c1, c2, c3 = st.columns(3)
        eposta = c1.text_input("E-posta", value=c.get("eposta") or "")
        pb = c2.selectbox("Para Birimi", ["TRY", "USD", "EUR", "GBP"],
                          index=["TRY", "USD", "EUR", "GBP"].index(c.get("para_birimi") or "TRY"))
        vade = c3.number_input("Ödeme Vadesi (gün)", value=int(c.get("odeme_vadesi_gun") or 0), step=1)
        teslim = tedarik = None
        if tip == "tedarikci":
            c1, c2 = st.columns(2)
            secenek = ["", "FOB", "CIF", "EXW", "DDP", "DAP"]
            teslim = c1.selectbox("Teslim Şekli", secenek,
                                  index=secenek.index(c.get("teslim_sekli") or ""))
            tedarik = c2.number_input("Tedarik Süresi (gün)",
                                      value=int(c.get("tedarik_suresi_gun") or 0), step=1)
        adres = st.text_area("Adres", value=c.get("adres") or "", height=70)
        notlar = st.text_input("Notlar", value=c.get("notlar") or "")

        if st.form_submit_button("Kaydet", type="primary"):
            if not unvan:
                st.error("Unvan zorunludur.")
                return
            kayit = {
                "tip": tip, "kod": kod or None, "unvan": unvan, "vergi_dairesi": vd or None,
                "vergi_no": vno or None, "ulke": ulke or None, "sehir": sehir or None,
                "yetkili_kisi": yetkili or None, "telefon": tel or None, "eposta": eposta or None,
                "para_birimi": pb, "odeme_vadesi_gun": vade, "adres": adres or None,
                "notlar": notlar or None,
            }
            if tip == "tedarikci":
                kayit["teslim_sekli"] = teslim or None
                kayit["tedarik_suresi_gun"] = tedarik or None
            try:
                if cari_id:
                    db.guncelle("cariler", kayit, [("id", "eq", cari_id)])
                else:
                    db.ekle("cariler", kayit)
                st.success("Kaydedildi.")
                st.rerun()
            except Exception as e:
                st.error(f"Kaydedilemedi: {e}")


# ---------------------------------------------------------------- cari hesaplar
def cari_hesaplar() -> None:
    ui.baslik("Cari Hesaplar", "borç / alacak takibi")

    bak = db.sorgu("v_cari_bakiye", sira="bakiye_try", tersine=True)
    vade = db.sorgu("v_vade_yaslandirma", sira="vade_tarihi")
    kasa = db.sorgu("kasa_banka", filtreler=[("aktif", "eq", True)])

    if not bak.empty:
        bak = bak[bak["bakiye_try"].fillna(0) != 0]
    borc = float(bak[bak["tip"] == "tedarikci"]["bakiye_try"].sum()) if not bak.empty else 0
    alacak = float(bak[bak["tip"] == "musteri"]["bakiye_try"].sum()) if not bak.empty else 0

    bandlar = ["guncel", "0-30", "31-60", "61-90", "90+"]
    band_ad = {"guncel": "Güncel", "0-30": "0-30 gün", "31-60": "31-60 gün",
               "61-90": "61-90 gün", "90+": "90+ gün"}
    band_renk = {"guncel": "#16a34a", "0-30": "#ca8a04", "31-60": "#ea580c",
                 "61-90": "#dc2626", "90+": "#1f2937"}
    yas = pd.DataFrame([{
        "Band": band_ad[b],
        "Tutar": float(vade[vade["yas_bandi"] == b]["genel_toplam"].sum()) if not vade.empty else 0,
        "Adet": int((vade["yas_bandi"] == b).sum()) if not vade.empty else 0,
        "renk": b,
    } for b in bandlar])

    ui.kpi_satiri([
        {"baslik": "Tedarikçi Borcu", "deger": ui.para0(borc), "alt": "", "renk": "kirmizi"},
        {"baslik": "Müşteri Alacağı", "deger": ui.para0(alacak), "alt": "", "renk": "yesil"},
        {"baslik": "90+ Gün Geciken",
         "deger": ui.para0(yas[yas["renk"] == "90+"]["Tutar"].iloc[0] if not yas.empty else 0),
         "alt": "", "renk": "kirmizi"},
        {"baslik": "Kasa / Banka",
         "deger": ui.para0(kasa[kasa["para_birimi"] == "TRY"]["bakiye"].sum()
                           if not kasa.empty else 0),
         "alt": "TRY hesaplar", "renk": "lacivert"},
    ], sutun=4)

    sol, sag = st.columns(2, gap="medium")
    with sol:
        st.markdown("##### Cari Bakiyeler")
        if bak.empty:
            st.info("Bakiyesi olan cari yok.")
        else:
            ui.tablo(pd.DataFrame({
                "Kod": bak["kod"], "Unvan": bak["unvan"],
                "Tip": bak["tip"].apply(lambda t: "Tedarikçi" if t == "tedarikci" else "Müşteri"),
                "Bakiye": bak["bakiye_try"],
                "Son Hareket": bak["son_hareket"].apply(ui.tarih_bicim),
            }), anahtar="cbak", indir="cari-bakiye", yukseklik=300,
                kolonlar={"Bakiye": ui.sayi_kolonu("Bakiye", 0, True)})
    with sag:
        st.markdown("##### Vade Yaşlandırma")
        ui.yatay_bar(yas[yas["Tutar"] > 0], "Band", "Tutar", "Band",
                     {band_ad[b]: band_renk[b] for b in bandlar},
                     yukseklik=200, sirala=False)
        if not vade.empty:
            gec = vade[vade["yas_bandi"] != "guncel"].head(15)
            if not gec.empty:
                st.markdown("###### Vadesi Geçen Faturalar")
                st.dataframe(pd.DataFrame({
                    "Cari": gec["unvan"], "Fatura": gec["fatura_no"],
                    "Gecikme": gec["gecikme_gun"].apply(lambda g: f"{int(g)} gün"),
                    "Tutar": gec["genel_toplam"],
                }), hide_index=True, width="stretch",
                    column_config={"Tutar": ui.sayi_kolonu("Tutar", 0, True)})
            else:
                st.success("Gecikmiş fatura yok 👍")
