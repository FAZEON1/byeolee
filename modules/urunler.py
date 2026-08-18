"""Ürün kataloğu — kozmetik özel alanlar dahil."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Ürünler", "katalog")
    M = auth.maliyet_gorur()

    stok = db.sorgu("v_urun_stok", sira="sku")
    ham = db.sorgu(
        "urunler",
        select="id,sku,ad,durum,urun_tipi,barkod_gtin,raf_omru_ay,pao_ay,net_miktar,birim,"
               "liste_fiyati,alis_fiyati,alis_para_birimi,tedarikci_id,min_stok,"
               "yeniden_siparis_nokta,tedarik_suresi_gun,kategori_id,marka_id",
    )
    if stok.empty:
        st.info("Katalogda ürün yok.")
        return
    df = stok.merge(ham, left_on="urun_id", right_on="id", how="left", suffixes=("", "_h"))

    c1, c2, c3 = st.columns(3)
    marka = c1.multiselect("Marka", sorted(df["marka"].dropna().unique()), key="ur_marka", placeholder="Tümü")
    kategori = c2.multiselect("Kategori", sorted(df["kategori"].dropna().unique()), key="ur_kat", placeholder="Tümü")
    durum = c3.multiselect("Durum", sorted(df["durum"].dropna().unique()),
                           default=["aktif"], format_func=lambda d: ui.DURUM_AD.get(d, d),
                           key="ur_durum", placeholder="Tümü")
    f = df
    if marka:
        f = f[f["marka"].isin(marka)]
    if kategori:
        f = f[f["kategori"].isin(kategori)]
    if durum:
        f = f[f["durum"].isin(durum)]

    gosterim = pd.DataFrame({
        "SKU": f["sku"],
        "Ürün": f["urun_adi"],
        "Marka": f["marka"],
        "Kategori": f["kategori"],
        "Barkod": f["barkod_gtin"],
        "Fiziksel": f["fiziksel"],
        "Rezerve": f["rezerve"],
        "Satılabilir": f["satilabilir"],
        "Parti": f["parti_sayisi"],
        "En Yakın SKT": f["en_yakin_skt"].apply(ui.tarih_bicim),
        "Sip. Noktası": f["yeniden_siparis_nokta"],
        "Satış Fiyatı": f["liste_fiyati"],
    })
    if M:
        gosterim["Stok Değeri"] = f["stok_degeri"]
    gosterim["Durum"] = f["durum"].apply(ui.durum_etiket)

    ui.tablo(gosterim, anahtar="urunler", indir="urunler", yukseklik=430, kolonlar={
        "Fiziksel": ui.sayi_kolonu("Fiziksel"),
        "Rezerve": ui.sayi_kolonu("Rezerve"),
        "Satılabilir": ui.sayi_kolonu("Satılabilir"),
        "Satış Fiyatı": ui.sayi_kolonu("Satış Fiyatı", 2, True),
        "Stok Değeri": ui.sayi_kolonu("Stok Değeri", 0, True),
    })

    st.markdown("---")
    sol, sag = st.columns([3, 1])
    secenekler = {int(r.urun_id): f"{r.sku} — {r.urun_adi}" for r in f.itertuples()}
    with sol:
        secili = ui.secim_kutusu("Ürün detayı", secenekler, "ur_secim", bos="— Ürün seçin —")
    with sag:
        st.write("")
        if auth.yetkili("katalog") and st.button("＋ Yeni Ürün", type="primary",
                                                 use_container_width=True):
            _form(None)
    if secili:
        _detay(int(secili))


def _detay(urun_id: int) -> None:
    M = auth.maliyet_gorur()
    u = db.tek("urunler", filtreler=[("id", "eq", urun_id)])
    s = db.tek("v_urun_stok", filtreler=[("urun_id", "eq", urun_id)]) or {}
    if not u:
        return
    partiler = db.sorgu("v_parti_stok", filtreler=[("urun_id", "eq", urun_id)], sira="skt")

    ort = None
    if M and s.get("fiziksel") and s.get("stok_degeri"):
        ort = float(s["stok_degeri"]) / float(s["fiziksel"])
    marj = None
    if ort and u.get("liste_fiyati"):
        marj = (float(u["liste_fiyati"]) - ort) / float(u["liste_fiyati"]) * 100

    kartlar = [
        {"baslik": "Fiziksel", "deger": ui.sayi_bicim(s.get("fiziksel")), "alt": "", "renk": "lacivert"},
        {"baslik": "Satılabilir", "deger": ui.sayi_bicim(s.get("satilabilir")), "alt": "", "renk": "yesil"},
    ]
    if M:
        kartlar += [
            {"baslik": "Ort. Maliyet", "deger": ui.para(ort), "alt": "", "renk": "gri"},
            {"baslik": "Brüt Marj",
             "deger": f"%{ui.sayi_bicim(marj, 1)}" if marj is not None else "—",
             "alt": "", "renk": "yesil" if (marj or 0) > 25 else "turuncu"},
        ]
    else:
        kartlar += [
            {"baslik": "Rezerve", "deger": ui.sayi_bicim(s.get("rezerve")), "alt": "", "renk": "gri"},
            {"baslik": "Parti", "deger": ui.sayi_bicim(s.get("parti_sayisi")), "alt": "", "renk": "gri"},
        ]
    ui.kpi_satiri(kartlar, sutun=4)

    t1, t2, t3 = st.tabs(["Genel", "Kozmetik Bilgileri", f"Partiler ({len(partiler)})"])
    with t1:
        bilgi = {
            "SKU": u["sku"], "Ürün Adı": u["ad"],
            "Marka": db.ref_secim("marka").get(u.get("marka_id"), "—"),
            "Kategori": db.ref_secim("kategori").get(u.get("kategori_id"), "—"),
            "Tedarikçi": db.ref_secim("tedarikci", "unvan").get(u.get("tedarikci_id"), "—"),
            "Barkod (GTIN)": u.get("barkod_gtin") or "—",
            "Menşei": u.get("mensei_ulke") or "—",
            "Net Miktar": f"{ui.sayi_bicim(u.get('net_miktar'), 2)} {u.get('birim') or ''}"
                          if u.get("net_miktar") else "—",
            "Liste Fiyatı": f"{ui.para(u.get('liste_fiyati'))} (KDV %{ui.sayi_bicim(u.get('kdv_orani'))})",
            "Min. Stok / Sipariş Noktası":
                f"{ui.sayi_bicim(u.get('min_stok'))} / {ui.sayi_bicim(u.get('yeniden_siparis_nokta'))}",
            "Tedarik Süresi": f"{ui.sayi_bicim(u.get('tedarik_suresi_gun'))} gün"
                              if u.get("tedarik_suresi_gun") else "—",
            "Durum": ui.durum_etiket(u.get("durum")),
        }
        if M and u.get("alis_fiyati"):
            bilgi["Alış Fiyatı"] = f"{ui.sayi_bicim(u['alis_fiyati'], 2)} {u.get('alis_para_birimi')}"
        st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                     hide_index=True, width="stretch")

    with t2:
        koz = {
            "Raf Ömrü": f"{u['raf_omru_ay']} ay" if u.get("raf_omru_ay") else "—",
            "PAO (açıldıktan sonra)": f"{u['pao_ay']}M" if u.get("pao_ay") else "—",
            "Min. satış raf ömrü": f"{u['min_satis_raf_omru_gun']} gün"
                                   if u.get("min_satis_raf_omru_gun") else "—",
            "Ürün Formu": u.get("urun_formu") or "—",
            "Saklama Koşulu": u.get("saklama_kosulu") or "—",
            "Tehlikeli Madde": "⚠️ Evet — kargo kısıtı olabilir" if u.get("tehlikeli_madde") else "Hayır",
            "Hedef Kitle": u.get("hedef_kitle") or "—",
            "Kullanım Alanı": ", ".join(u.get("kullanim_alani") or []) or "—",
            "Sertifikalar": ", ".join(u.get("sertifikalar") or []) or "—",
            "Bildirim No": u.get("bildirim_no") or "—",
            "Alerjen Uyarısı": u.get("alerjen_notu") or "—",
            "INCI İçerik": u.get("inci_icerik") or "—",
            "Ağırlık / Boyut": (f"{ui.sayi_bicim(u.get('agirlik_gr'), 1)} gr" if u.get("agirlik_gr") else "—")
                               + (f" · {u.get('en_cm')}×{u.get('boy_cm')}×{u.get('yukseklik_cm')} cm"
                                  if u.get("en_cm") else ""),
            "Koli İçi": f"{u['koli_ici_adet']} adet" if u.get("koli_ici_adet") else "—",
        }
        st.dataframe(pd.DataFrame({"Alan": list(koz), "Değer": [str(v) for v in koz.values()]}),
                     hide_index=True, width="stretch")

    with t3:
        if partiler.empty:
            st.info("Parti kaydı yok.")
        else:
            g = pd.DataFrame({
                "Parti No": partiler["parti_no"],
                "SKT": partiler["skt"].apply(ui.tarih_bicim),
                "Durum (SKT)": partiler.apply(
                    lambda r: ui.skt_etiket(r["skt_renk"], r["kalan_gun"]), axis=1),
                "Parti Durumu": partiler["durum"].apply(ui.durum_etiket),
                "Fiziksel": partiler["fiziksel"],
                "Satılabilir": partiler["satilabilir"],
            })
            if M:
                g["Birim Maliyet"] = partiler["birim_maliyet"]
            st.dataframe(g, hide_index=True, width="stretch",
                         column_config={"Birim Maliyet": ui.sayi_kolonu("Birim Maliyet", 2, True)})

    if auth.yetkili("katalog"):
        if st.button("✎ Ürünü Düzenle", key="ur_duzenle"):
            _form(urun_id)


@st.dialog("Ürün Kartı", width="large")
def _form(urun_id: int | None) -> None:
    u = db.tek("urunler", filtreler=[("id", "eq", urun_id)]) if urun_id else {}
    u = u or {}
    with st.form("urun_form"):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU *", value=u.get("sku") or "")
        barkod = c2.text_input("Barkod (GTIN)", value=u.get("barkod_gtin") or "")
        ad = st.text_input("Ürün Adı *", value=u.get("ad") or "")

        c1, c2, c3 = st.columns(3)
        with c1:
            marka_id = ui.secim_kutusu("Marka", db.ref_secim("marka"), "f_marka",
                                       varsayilan=u.get("marka_id"))
        with c2:
            kat_id = ui.secim_kutusu("Kategori", db.ref_secim("kategori"), "f_kat",
                                     varsayilan=u.get("kategori_id"))
        with c3:
            ted_id = ui.secim_kutusu("Tedarikçi", db.ref_secim("tedarikci", "unvan"), "f_ted",
                                     varsayilan=u.get("tedarikci_id"))

        c1, c2, c3, c4 = st.columns(4)
        net = c1.number_input("Net Miktar", value=float(u.get("net_miktar") or 0), step=1.0)
        birim = c2.selectbox("Birim", ["adet", "ml", "gr"],
                             index=["adet", "ml", "gr"].index(u.get("birim") or "adet"))
        raf = c3.number_input("Raf Ömrü (ay)", value=int(u.get("raf_omru_ay") or 0), step=1)
        pao = c4.number_input("PAO (ay)", value=int(u.get("pao_ay") or 0), step=1)

        c1, c2, c3, c4 = st.columns(4)
        liste = c1.number_input("Liste Fiyatı ₺", value=float(u.get("liste_fiyati") or 0), step=1.0)
        alis = c2.number_input("Alış Fiyatı", value=float(u.get("alis_fiyati") or 0), step=0.01)
        pb = c3.selectbox("Alış Dövizi", ["TRY", "USD", "EUR", "GBP"],
                          index=["TRY", "USD", "EUR", "GBP"].index(u.get("alis_para_birimi") or "TRY"))
        kdv = c4.number_input("KDV %", value=float(u.get("kdv_orani") or 20), step=1.0)

        c1, c2, c3, c4 = st.columns(4)
        min_stok = c1.number_input("Min. Stok", value=int(u.get("min_stok") or 0), step=1)
        rop = c2.number_input("Sipariş Noktası", value=int(u.get("yeniden_siparis_nokta") or 0), step=1)
        tedarik = c3.number_input("Tedarik Süresi (gün)", value=int(u.get("tedarik_suresi_gun") or 0), step=1)
        min_omur = c4.number_input("Min. Satış Raf Ömrü (gün)",
                                   value=int(u.get("min_satis_raf_omru_gun") or 0), step=1,
                                   help="Bu sürenin altındaki parti satılamaz")

        c1, c2, c3 = st.columns(3)
        form = c1.text_input("Ürün Formu", value=u.get("urun_formu") or "",
                             placeholder="krem, serum, sıvı…")
        saklama = c2.text_input("Saklama Koşulu", value=u.get("saklama_kosulu") or "")
        durum = c3.selectbox("Durum", ["aktif", "pasif", "askida"],
                             index=["aktif", "pasif", "askida"].index(u.get("durum") or "aktif"),
                             format_func=lambda d: ui.DURUM_AD.get(d, d))

        alerjen = st.text_input("Alerjen Uyarısı", value=u.get("alerjen_notu") or "")
        inci = st.text_area("INCI İçerik", value=u.get("inci_icerik") or "", height=70)
        tehlikeli = st.checkbox("Tehlikeli madde (aerosol / alkol bazlı / yanıcı)",
                                value=bool(u.get("tehlikeli_madde")))

        if st.form_submit_button("Kaydet", type="primary"):
            if not sku or not ad:
                st.error("SKU ve ürün adı zorunludur.")
                return
            kayit = {
                "sku": sku.strip(), "ad": ad.strip(), "barkod_gtin": barkod or None,
                "marka_id": marka_id, "kategori_id": kat_id, "tedarikci_id": ted_id,
                "net_miktar": net or None, "birim": birim,
                "raf_omru_ay": raf or None, "pao_ay": pao or None,
                "liste_fiyati": liste or None, "alis_fiyati": alis or None,
                "alis_para_birimi": pb, "kdv_orani": kdv,
                "min_stok": min_stok, "yeniden_siparis_nokta": rop,
                "tedarik_suresi_gun": tedarik or None,
                "min_satis_raf_omru_gun": min_omur or None,
                "urun_formu": form or None, "saklama_kosulu": saklama or None,
                "alerjen_notu": alerjen or None, "inci_icerik": inci or None,
                "tehlikeli_madde": tehlikeli, "durum": durum,
            }
            try:
                if urun_id:
                    db.guncelle("urunler", kayit, [("id", "eq", urun_id)])
                else:
                    db.ekle("urunler", kayit)
                st.success("Kaydedildi.")
                st.rerun()
            except Exception as e:
                st.error(f"Kaydedilemedi: {e}")
