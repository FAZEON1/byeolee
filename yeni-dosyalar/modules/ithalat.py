"""İthalat dosyası ve landed cost (gerçek birim maliyet) hesabı."""
from __future__ import annotations

import random
import string
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui

KUR_VARSAYILAN = {"TRY": 1.0, "USD": 41.80, "EUR": 48.50, "GBP": 56.20}


def goster() -> None:
    ui.baslik("İthalat & Maliyetlendirme", "landed cost")
    M = auth.maliyet_gorur()

    ui.kural_notu(
        "🚢 <b>Landed cost = mal bedeli + navlun + gümrük + sigorta + tüm masraflar.</b> "
        "Masraflar seçtiğiniz dağıtım anahtarına göre (bedel / adet / ağırlık / hacim) kalemlere "
        "yayılır ve ilgili partinin birim maliyeti olarak yazılır. Sonradan gelen faturalar "
        "maliyeti revize eder ve revizyon loglanır (BR-08)."
    )

    if auth.yetkili("satinalma") and st.button("＋ Yeni İthalat Dosyası", type="primary"):
        st.session_state["ith_form"] = True
    if st.session_state.get("ith_form"):
        _form()

    df = db.sorgu("v_ithalat_maliyet", sira="dosya_id", tersine=True)
    if df.empty:
        st.info("İthalat dosyası yok.")
        return
    ham = db.sorgu("ithalat_dosyalari", select="id,dagitim_yapildi")
    dagitim = dict(zip(ham["id"], ham["dagitim_yapildi"])) if not ham.empty else {}
    df = df.copy()
    df["dagitim_yapildi"] = df["dosya_id"].map(dagitim).fillna(False)

    t = pd.DataFrame({
        "Dosya No": df["dosya_no"],
        "Tedarikçi": df["tedarikci"],
        "Durum": df["durum"].apply(ui.durum_etiket),
        "Kalem": df["kalem_sayisi"],
    })
    if M:
        t["Mal Bedeli"] = df["mal_bedeli_try"]
        t["Masraf"] = df["toplam_masraf_try"]
        t["Masraf %"] = df["masraf_orani_yuzde"]
        t["Landed Cost"] = df["toplam_landed_try"]
    t["Dağıtım"] = df["dagitim_yapildi"].apply(lambda x: "🟢 Yapıldı" if x else "🟡 Bekliyor")

    ui.tablo(t, anahtar="ith", indir="ithalat", yukseklik=290, kolonlar={
        "Mal Bedeli": ui.sayi_kolonu("Mal Bedeli", 0, True),
        "Masraf": ui.sayi_kolonu("Masraf", 0, True),
        "Masraf %": ui.sayi_kolonu("Masraf %", 1),
        "Landed Cost": ui.sayi_kolonu("Landed Cost", 0, True),
    })

    st.markdown("---")
    secenekler = {int(r.dosya_id): f"{r.dosya_no} — {r.tedarikci or ''}" for r in df.itertuples()}
    secili = ui.secim_kutusu("Dosya detayı", secenekler, "ith_secim", bos="— Dosya seçin —")
    if secili:
        _detay(int(secili))


def _detay(dosya_id: int) -> None:
    M = auth.maliyet_gorur()
    d = db.tek("ithalat_dosyalari", select="*, cariler(unvan,ulke)",
               filtreler=[("id", "eq", dosya_id)])
    kalem = db.sorgu("ithalat_kalemleri", select="*, urunler(sku,ad), partiler(parti_no,skt)",
                     filtreler=[("dosya_id", "eq", dosya_id)])
    masraf = db.sorgu("ithalat_masraflar", filtreler=[("dosya_id", "eq", dosya_id)], sira="id")
    if not d:
        return

    if not d.get("dagitim_yapildi") and not kalem.empty:
        st.warning("**Maliyet dağıtımı henüz yapılmadı.** 'Maliyeti Dağıt' ile birim landed cost "
                   "hesaplanır ve partilere yazılır.", icon="⚠️")

    if M:
        dahil = masraf[masraf["maliyete_dahil"]] if not masraf.empty else pd.DataFrame()
        haric = masraf[~masraf["maliyete_dahil"]] if not masraf.empty else pd.DataFrame()
        msf = float(dahil["tutar_try"].sum()) if not dahil.empty else 0.0
        kdv = float(haric["tutar_try"].sum()) if not haric.empty else 0.0
        mal = float(d.get("mal_bedeli_try") or 0)
        ui.kpi_satiri([
            {"baslik": "Mal Bedeli", "deger": ui.para0(mal), "alt": "", "renk": "lacivert"},
            {"baslik": "Toplam Masraf", "deger": ui.para0(msf), "alt": "maliyete dahil",
             "renk": "turuncu"},
            {"baslik": "İndirilecek KDV", "deger": ui.para0(kdv), "alt": "maliyete dahil değil",
             "renk": "gri"},
            {"baslik": "Landed Cost", "deger": ui.para0(d.get("toplam_landed_try")),
             "alt": f"+%{ui.sayi_bicim(msf / mal * 100, 1)}" if mal else "", "renk": "yesil"},
        ], sutun=4)

    t1, t2, t3, t4 = st.tabs(["Dosya Bilgileri", f"Ürün Kalemleri ({len(kalem)})",
                              f"Masraflar ({len(masraf)})", "Süreç Takvimi"])
    with t1:
        bilgi = {
            "Tedarikçi": f"{(d.get('cariler') or {}).get('unvan','—')} "
                         f"({(d.get('cariler') or {}).get('ulke','')})",
            "Durum": ui.durum_etiket(d["durum"]),
            "Proforma / Fatura": f"{d.get('proforma_no') or '—'} / {d.get('fatura_no') or '—'}",
            "Teslim Şekli": f"{d.get('teslim_sekli') or '—'} · {d.get('sevkiyat_tipi') or '—'}",
            "Konteyner / AWB": d.get("konteyner_no") or "—",
            "Liman": f"{d.get('cikis_limani') or '—'} → {d.get('varis_limani') or '—'}",
            "Gümrük": d.get("gumruk_mudurlugu") or "—",
            "Beyanname": f"{d.get('beyanname_no') or '—'} "
                         f"({ui.tarih_bicim(d.get('beyanname_tarihi'))})",
            "Gümrük Müşaviri": d.get("gumruk_musaviri") or "—",
            "Kur": f"{d.get('para_birimi')} × {ui.sayi_bicim(d.get('kur'), 2)}",
        }
        st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                     hide_index=True, width="stretch")

    with t2:
        if kalem.empty:
            st.info("Kalem yok.")
        else:
            kur = float(d.get("kur") or 1)
            fob_try = kalem["birim_fob"].astype(float) * kur
            artis = (kalem["birim_landed_try"].astype(float) / fob_try.replace(0, pd.NA) - 1) * 100
            g = pd.DataFrame({
                "SKU": kalem["urunler"].apply(lambda x: (x or {}).get("sku")),
                "Ürün": kalem["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 32),
                "Adet": kalem["adet"],
                "Birim FOB": kalem["birim_fob"],
            })
            if M:
                g["Mal Bedeli ₺"] = kalem["mal_bedeli_try"]
                g["Dağıtılan Masraf"] = kalem["dagitilan_masraf_try"]
                g["Birim Landed ₺"] = kalem["birim_landed_try"]
                g["Artış %"] = artis.round(1)
            g["Parti"] = kalem["partiler"].apply(lambda x: (x or {}).get("parti_no") or "—")
            st.dataframe(g, hide_index=True, width="stretch", column_config={
                "Adet": ui.sayi_kolonu("Adet"),
                "Birim FOB": ui.sayi_kolonu("Birim FOB", 2),
                "Mal Bedeli ₺": ui.sayi_kolonu("Mal Bedeli ₺", 0, True),
                "Dağıtılan Masraf": ui.sayi_kolonu("Dağıtılan Masraf", 0, True),
                "Birim Landed ₺": ui.sayi_kolonu("Birim Landed ₺", 2, True),
                "Artış %": ui.sayi_kolonu("Artış %", 1),
            })

    with t3:
        if masraf.empty:
            st.info("Masraf kalemi yok.")
        else:
            adlar = {m["kod"]: m["ad"] for m in db.ref()["masraf"]}
            st.dataframe(pd.DataFrame({
                "Kalem": masraf["kalem_tipi"].map(adlar).fillna(masraf["kalem_tipi"]),
                "Açıklama": masraf["aciklama"].fillna("—"),
                "Tutar": masraf["tutar"],
                "Döviz": masraf["doviz_kodu"],
                "₺ Karşılık": masraf["tutar_try"],
                "Dağıtım Anahtarı": masraf["dagitim"].map(ui.DAGITIM_AD),
                "Maliyete": masraf["maliyete_dahil"].apply(lambda x: "🟢 Dahil" if x else "⚪ Hariç"),
                "Belge": masraf["belge_no"].fillna("—"),
            }), hide_index=True, width="stretch", column_config={
                "Tutar": ui.sayi_kolonu("Tutar", 2),
                "₺ Karşılık": ui.sayi_kolonu("₺ Karşılık", 0, True),
            })

    with t4:
        takvim = {
            "Sipariş": ui.tarih_bicim(d.get("siparis_tarihi")),
            "Yükleme": ui.tarih_bicim(d.get("yukleme_tarihi")),
            "Tahmini Varış (ETA)": ui.tarih_bicim(d.get("eta")),
            "Gerçek Varış": ui.tarih_bicim(d.get("gercek_varis")),
            "Gümrükleme": ui.tarih_bicim(d.get("gumrukleme_tarihi")),
            "Depo Girişi": ui.tarih_bicim(d.get("depo_giris_tarihi")),
        }
        if d.get("siparis_tarihi") and d.get("depo_giris_tarihi"):
            gun = (pd.Timestamp(d["depo_giris_tarihi"]) - pd.Timestamp(d["siparis_tarihi"])).days
            takvim["Toplam Süre"] = f"{gun} gün"
        st.dataframe(pd.DataFrame({"Aşama": list(takvim), "Tarih": list(takvim.values())}),
                     hide_index=True, width="stretch")

    if auth.yetkili("satinalma"):
        c1, c2 = st.columns(2)
        if c1.button("＋ Masraf Ekle", key="ith_masraf", use_container_width=True):
            _masraf_ekle(dosya_id)
        if not kalem.empty and c2.button("⟳ Maliyeti Dağıt", type="primary",
                                         key="ith_dagit", use_container_width=True):
            _dagit(dosya_id)


@st.dialog("Maliyeti Dağıt")
def _dagit(dosya_id: int) -> None:
    st.info("Tüm masraflar seçilen dağıtım anahtarlarına göre kalemlere yayılacak ve "
            "**ilgili partilerin birim maliyeti güncellenecek**. Maliyet değişirse "
            "revizyon kaydı oluşturulur (BR-08).")
    if st.button("Dağıt", type="primary"):
        try:
            s = db.rpc("landed_cost_dagit", {"p_dosya_id": dosya_id})
            st.success(f"{s.get('kalem_sayisi')} kalem için birim landed cost hesaplandı.")
            mal = float(s.get("mal_bedeli_try") or 0)
            msf = float(s.get("toplam_masraf_try") or 0)
            st.write(f"- Mal bedeli: **{ui.para(mal)}**")
            st.write(f"- Toplam masraf: **{ui.para(msf)}**")
            st.write(f"- Toplam landed cost: **{ui.para(s.get('toplam_landed_try'))}**")
            if mal:
                st.write(f"- Masraf oranı: **%{ui.sayi_bicim(msf / mal * 100, 2)}**")
            st.rerun()
        except Exception as e:
            st.error(f"Dağıtılamadı: {e}")


@st.dialog("Masraf Kalemi Ekle")
def _masraf_ekle(dosya_id: int) -> None:
    kalemler = db.ref()["masraf"]
    secim = st.selectbox("Masraf Kalemi *", kalemler, format_func=lambda m: m["ad"])
    aciklama = st.text_input("Açıklama")
    c1, c2, c3 = st.columns(3)
    tutar = c1.number_input("Tutar *", min_value=0.0, step=100.0)
    doviz = c2.selectbox("Döviz", ["TRY", "USD", "EUR", "GBP"])
    kur = c3.number_input("Kur", value=KUR_VARSAYILAN.get(doviz, 1.0), step=0.01)
    c1, c2 = st.columns(2)
    dagitim = c1.selectbox(
        "Dağıtım Anahtarı *", ["mal_bedeli", "adet", "agirlik", "hacim", "esit"],
        index=["mal_bedeli", "adet", "agirlik", "hacim", "esit"].index(
            secim["varsayilan_dagitim"]) if secim["varsayilan_dagitim"] in
            ["mal_bedeli", "adet", "agirlik", "hacim", "esit"] else 0,
        format_func=lambda d: ui.DAGITIM_AD.get(d, d),
        help="Navlun genelde hacme, gümrük vergisi mal bedeline göre dağıtılır.")
    belge = c2.text_input("Belge No")
    dahil = st.checkbox("Maliyete dahil et (KDV için işaretlemeyin — indirilecek KDV)",
                        value=bool(secim["maliyete_dahil"]))
    gec = st.checkbox("Sonradan gelen fatura (maliyet revize edilecek)")

    if st.button("Ekle", type="primary"):
        if tutar <= 0:
            st.error("Tutar gerekli.")
            return
        try:
            db.ekle("ithalat_masraflar", {
                "dosya_id": dosya_id, "kalem_tipi": secim["kod"], "aciklama": aciklama or None,
                "tutar": tutar, "doviz_kodu": doviz, "kur": kur, "dagitim": dagitim,
                "maliyete_dahil": dahil, "belge_no": belge or None, "gec_gelen": gec,
            })
            st.success("Masraf eklendi. Maliyeti yeniden dağıtmayı unutmayın.")
            st.rerun()
        except Exception as e:
            st.error(f"Eklenemedi: {e}")


@st.dialog("Yeni İthalat Dosyası", width="large")
def _form() -> None:
    sa = db.sorgu("satin_alma_siparisleri", select="id,siparis_no,tedarikci_id,para_birimi,kur",
                  filtreler=[("durum", "in", "(taslak,onaylandi,kismen_teslim)")],
                  sira="siparis_no", tersine=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        no = st.text_input("Dosya No *",
                           value=f"ITH-{date.today().year}-{random.randint(100, 999)}")
    with c2:
        ted_id = ui.secim_kutusu("Tedarikçi *", db.ref_secim("tedarikci", "unvan"),
                                 "id_ted", bos=None)
    with c3:
        sa_id = ui.secim_kutusu(
            "Satın Alma Siparişi",
            {int(r.id): r.siparis_no for r in sa.itertuples()} if not sa.empty else {},
            "id_sa", bos="— Yok —")

    c1, c2, c3, c4 = st.columns(4)
    teslim = c1.selectbox("Teslim Şekli", ["FOB", "CIF", "EXW", "DDP", "DAP"])
    sevkiyat = c2.selectbox("Sevkiyat", ["deniz", "hava", "kara"])
    pb = c3.selectbox("Para Birimi", ["USD", "EUR", "TRY", "GBP"], index=1)
    kur = c4.number_input("Kur *", value=KUR_VARSAYILAN.get(pb, 1.0), step=0.01)

    c1, c2, c3, c4 = st.columns(4)
    proforma = c1.text_input("Proforma No")
    konteyner = c2.text_input("Konteyner / AWB")
    cikis = c3.text_input("Çıkış Limanı")
    varis = c4.text_input("Varış Limanı", value="Ambarlı")

    c1, c2, c3 = st.columns(3)
    tarih = c1.date_input("Sipariş Tarihi", value=date.today(), format="DD.MM.YYYY")
    eta = c2.date_input("ETA", value=date.today() + timedelta(days=40), format="DD.MM.YYYY")
    musavir = c3.text_input("Gümrük Müşaviri")

    st.caption("Dosya oluşturulduktan sonra ürün kalemleri satın alma siparişinden aktarılır; "
               "masrafları ekleyip maliyeti dağıtabilirsiniz.")

    c1, c2 = st.columns([1, 3])
    if c1.button("Vazgeç"):
        st.session_state.pop("ith_form", None)
        st.rerun()
    if c2.button("Oluştur", type="primary"):
        if not ted_id:
            st.error("Tedarikçi seçilmelidir.")
            return
        try:
            dos = db.ekle("ithalat_dosyalari", {
                "dosya_no": no, "tedarikci_id": ted_id, "satin_alma_id": sa_id,
                "proforma_no": proforma or None, "teslim_sekli": teslim,
                "sevkiyat_tipi": sevkiyat, "konteyner_no": konteyner or None,
                "cikis_limani": cikis or None, "varis_limani": varis or None,
                "gumruk_musaviri": musavir or None, "para_birimi": pb, "kur": kur,
                "siparis_tarihi": str(tarih), "eta": str(eta), "durum": "acik",
                "olusturan": db.kullanici_id(),
            })[0]
            if sa_id:
                sat = db.sorgu(
                    "satin_alma_satirlar",
                    select="urun_id,adet,birim_fiyat, urunler(agirlik_gr,en_cm,boy_cm,yukseklik_cm)",
                    filtreler=[("siparis_id", "eq", sa_id)])
                if not sat.empty:
                    kalemler = []
                    for r in sat.itertuples():
                        u = r.urunler or {}
                        adet = float(r.adet)
                        kalemler.append({
                            "dosya_id": dos["id"], "urun_id": int(r.urun_id), "adet": adet,
                            "birim_fob": float(r.birim_fiyat or 0),
                            "toplam_agirlik_kg": adet * float(u.get("agirlik_gr") or 0) / 1000 or None,
                            "toplam_hacim_cbm": (
                                adet * float(u.get("en_cm") or 0) * float(u.get("boy_cm") or 0)
                                * float(u.get("yukseklik_cm") or 0) / 1e6) or None,
                        })
                    db.ekle("ithalat_kalemleri", kalemler)
            st.success(f"Dosya oluşturuldu: {no}")
            st.session_state.pop("ith_form", None)
            st.rerun()
        except Exception as e:
            st.error(f"Oluşturulamadı: {e}")
