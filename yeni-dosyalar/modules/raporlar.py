"""Rapor merkezi — 15 rapor."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui

RAPORLAR = {
    "SKT & Parti": {
        "skt": "SKT Yaklaşan Ürünler",
        "sktgecmis": "SKT Geçmiş Stok ve Kaybı",
        "rafomru": "Raf Ömrü Dağılımı",
        "imha": "İmha / Fire Raporu",
    },
    "Stok": {
        "stok": "Stok Değerleme",
        "kritik": "Kritik Stok / Sipariş Önerisi",
        "olu": "Ölü ve Yavaş Dönen Stok",
        "devir": "Stok Devir Hızı",
        "abc": "ABC Analizi",
    },
    "Satış": {
        "satis": "Satış Raporu",
        "karlilik": "Kârlılık (komisyon sonrası)",
        "kanal": "Kanal Karşılaştırma",
        "iade": "İade Analizi",
    },
    "Tedarik": {
        "ithalat": "İthalat Maliyet Dağılımı",
        "maliyet": "Ürün Maliyet Geçmişi",
    },
}


def goster() -> None:
    ui.baslik("Raporlar", "")
    tumu = {k: v for grup in RAPORLAR.values() for k, v in grup.items()}
    gruplu = [(g, k) for g, raporlar in RAPORLAR.items() for k in raporlar]

    secim = st.selectbox(
        "Rapor seçin", [k for _, k in gruplu],
        format_func=lambda k: f"{[g for g, kk in gruplu if kk == k][0]} › {tumu[k]}",
        key="rp_secim",
    )
    st.markdown(f"#### {tumu[secim]}")
    globals()[f"_r_{secim}"]()


# ---------------------------------------------------------------- SKT
def _skt_tablo(sadece_gecmis: bool) -> None:
    M = auth.maliyet_gorur()
    df = db.sorgu("v_skt_uyari", filtreler=[("fiziksel", "gt", 0)], sira="skt")
    if df.empty:
        st.info("Kayıt yok.")
        return
    df = df[df["skt_renk"] == "siyah"] if sadece_gecmis \
        else df[df["skt_renk"].isin(["kirmizi", "turuncu", "sari"])]
    if df.empty:
        st.success("Bu bantta parti yok 👍")
        return

    toplam = float(df["risk_tutari"].fillna(0).sum()) if M else 0
    ui.kpi_satiri([
        {"baslik": "Parti Sayısı", "deger": str(len(df)), "alt": "",
         "renk": "kirmizi" if sadece_gecmis else "turuncu"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(df["fiziksel"].sum()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Kayıp Tutarı" if sadece_gecmis else "Risk Tutarı",
         "deger": ui.para0(toplam) if M else "•••", "alt": "", "renk": "kirmizi"},
        {"baslik": "Etkilenen Ürün", "deger": str(df["sku"].nunique()), "alt": "", "renk": "gri"},
    ], sutun=4)

    if sadece_gecmis:
        st.error("Bu stok satılamaz. İmha kararı veya tedarikçi iadesi gerekiyor.", icon="⚠️")

    t = pd.DataFrame({
        "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 40), "Marka": df["marka"],
        "Parti": df["parti_no"], "SKT": df["skt"].apply(ui.tarih_bicim),
        "Durum": df.apply(lambda r: ui.skt_etiket(r["skt_renk"], r["kalan_gun"]), axis=1),
        "Kalan Gün": df["kalan_gun"], "Stok": df["fiziksel"],
    })
    if M:
        t["Risk Tutarı"] = df["risk_tutari"]
    ui.tablo(t, anahtar="rp_skt", indir="skt-raporu", yukseklik=420, kolonlar={
        "Kalan Gün": ui.sayi_kolonu("Kalan Gün"), "Stok": ui.sayi_kolonu("Stok"),
        "Risk Tutarı": ui.sayi_kolonu("Risk Tutarı", 0, True)})


def _r_skt() -> None:
    _skt_tablo(False)


def _r_sktgecmis() -> None:
    _skt_tablo(True)


def _r_rafomru() -> None:
    M = auth.maliyet_gorur()
    df = db.sorgu("v_skt_uyari", filtreler=[("fiziksel", "gt", 0)])
    if df.empty:
        st.info("Kayıt yok.")
        return
    bantlar = [("siyah", "SKT geçmiş"), ("kirmizi", "0-30 gün"), ("turuncu", "31-90 gün"),
               ("sari", "91-180 gün"), ("yesil", "180+ gün")]
    satirlar = []
    for k, ad in bantlar:
        g = df[df["skt_renk"] == k]
        satirlar.append({
            "Band": f"{ui.SKT_NOKTA[k]} {ad}", "Parti": len(g),
            "Adet": int(g["fiziksel"].sum()),
            "Değer": float(g["risk_tutari"].fillna(0).sum()) if M else 0.0, "renk": k,
        })
    b = pd.DataFrame(satirlar)
    ui.yatay_bar(b[b["Adet"] > 0], "Band", "Değer" if M else "Adet", "Band",
                 {r["Band"]: ui.RENK[r["renk"]] for r in satirlar},
                 yukseklik=230, sirala=False)
    top_adet = b["Adet"].sum() or 1
    top_deger = b["Değer"].sum() or 1
    b["% Adet"] = (b["Adet"] / top_adet * 100).round(1)
    if M:
        b["% Değer"] = (b["Değer"] / top_deger * 100).round(1)
    st.dataframe(b.drop(columns=["renk"] + ([] if M else ["Değer"])),
                 hide_index=True, width="stretch",
                 column_config={"Değer": ui.sayi_kolonu("Değer", 0, True)})


def _r_imha() -> None:
    M = auth.maliyet_gorur()
    df = db.sorgu("imha_kayitlari", select="*, partiler(parti_no,skt, urunler(sku,ad))",
                  sira="tarih", tersine=True)
    if df.empty:
        st.info("İmha kaydı yok.")
        return
    zarar = df["miktar"] * df["birim_maliyet"].fillna(0)
    ui.kpi_satiri([
        {"baslik": "İmha Kaydı", "deger": str(len(df)), "alt": "", "renk": "kirmizi"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(df["miktar"].sum()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Toplam Zarar", "deger": ui.para0(zarar.sum()) if M else "•••", "alt": "",
         "renk": "kirmizi"},
    ], sutun=3)
    t = pd.DataFrame({
        "Tarih": df["tarih"].apply(ui.tarih_bicim),
        "SKU": df["partiler"].apply(lambda x: ((x or {}).get("urunler") or {}).get("sku")),
        "Ürün": df["partiler"].apply(
            lambda x: ((x or {}).get("urunler") or {}).get("ad") or "").str.slice(0, 36),
        "Parti": df["partiler"].apply(lambda x: (x or {}).get("parti_no")),
        "Miktar": df["miktar"], "Sebep": df["sebep"],
    })
    if M:
        t["Zarar"] = zarar
    ui.tablo(t, anahtar="rp_imha", indir="imha", kolonlar={
        "Miktar": ui.sayi_kolonu("Miktar"), "Zarar": ui.sayi_kolonu("Zarar", 2, True)})


# ---------------------------------------------------------------- stok
def _r_stok() -> None:
    M = auth.maliyet_gorur()
    df = db.sorgu("v_urun_stok", filtreler=[("fiziksel", "gt", 0)], sira="sku")
    if df.empty:
        st.info("Stokta ürün yok.")
        return
    satis_degeri = df["fiziksel"] * df["liste_fiyati"].fillna(0)
    maliyet = float(df["stok_degeri"].fillna(0).sum()) if M else 0
    ui.kpi_satiri([
        {"baslik": "Ürün Çeşidi", "deger": str(len(df)), "alt": "", "renk": "lacivert"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(df["fiziksel"].sum()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Maliyet Değeri", "deger": ui.para0(maliyet) if M else "•••", "alt": "",
         "renk": "gri"},
        {"baslik": "Satış Değeri", "deger": ui.para0(satis_degeri.sum()), "alt": "",
         "renk": "yesil"},
    ] + ([{"baslik": "Potansiyel Brüt Kâr", "deger": ui.para0(satis_degeri.sum() - maliyet),
           "alt": f"%{ui.sayi_bicim((satis_degeri.sum() - maliyet) / satis_degeri.sum() * 100, 1)}"
                  if satis_degeri.sum() else "", "renk": "yesil"}] if M else []), sutun=5)

    t = pd.DataFrame({
        "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 40),
        "Marka": df["marka"], "Kategori": df["kategori"],
        "Parti": df["parti_sayisi"], "Fiziksel": df["fiziksel"], "Satılabilir": df["satilabilir"],
    })
    if M:
        t["Ort. Maliyet"] = (df["stok_degeri"] / df["fiziksel"].replace(0, pd.NA)).round(2)
        t["Maliyet Değeri"] = df["stok_degeri"]
    t["Satış Değeri"] = satis_degeri
    ui.tablo(t, anahtar="rp_stok", indir="stok-degerleme", yukseklik=430, kolonlar={
        "Fiziksel": ui.sayi_kolonu("Fiziksel"), "Satılabilir": ui.sayi_kolonu("Satılabilir"),
        "Ort. Maliyet": ui.sayi_kolonu("Ort. Maliyet", 2, True),
        "Maliyet Değeri": ui.sayi_kolonu("Maliyet Değeri", 0, True),
        "Satış Değeri": ui.sayi_kolonu("Satış Değeri", 0, True)})


def _r_kritik() -> None:
    df = db.sorgu("v_kritik_stok")
    dev = db.sorgu("v_stok_devir")
    if df.empty:
        st.success("Kritik stokta ürün yok 👍")
        return
    if not dev.empty:
        df = df.merge(dev[["urun_id", "satis_90g", "tahmini_tukenme_gun"]], on="urun_id", how="left")
    st.info("Satılabilir stoğu sipariş noktasının altına düşen ürünler. Tahmini tükenme, "
            "son 90 günlük satış hızına göre hesaplanır.", icon="📉")
    t = pd.DataFrame({
        "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 40), "Marka": df["marka"],
        "Satılabilir": df["satilabilir"], "Min Stok": df["min_stok"],
        "Sipariş Noktası": df["yeniden_siparis_nokta"],
        "Önerilen Sipariş": df["eksik_adet"].clip(lower=0),
        "90 Gün Satış": df.get("satis_90g"),
        "Tahmini Tükenme": df.get("tahmini_tukenme_gun"),
    })
    ui.tablo(t, anahtar="rp_kritik", indir="kritik-stok", yukseklik=420)


def _r_olu() -> None:
    M = auth.maliyet_gorur()
    esik = int(db.ayar("olu_stok_gun", 120) or 120)
    df = db.sorgu("v_olu_stok", filtreler=[("hareketsiz_gun", "gte", esik)],
                  sira="stok_degeri", tersine=True)
    if df.empty:
        st.success(f"{esik} günden uzun hareketsiz stok yok 👍")
        return
    ui.kpi_satiri([
        {"baslik": "Ölü Stok Ürünü", "deger": str(len(df)), "alt": f"{esik}+ gün hareketsiz",
         "renk": "turuncu"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(df["fiziksel"].sum()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Bağlı Sermaye",
         "deger": ui.para0(df["stok_degeri"].fillna(0).sum()) if M else "•••",
         "alt": "", "renk": "kirmizi"},
    ], sutun=3)
    t = pd.DataFrame({
        "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 40),
        "Marka": df["marka"], "Kategori": df["kategori"], "Stok": df["fiziksel"],
        "Hareketsiz": df["hareketsiz_gun"].apply(
            lambda x: "hiç satılmadı" if x > 9000 else f"{int(x)} gün"),
        "Son Satış": df["son_hareket"].apply(ui.tarih_bicim),
    })
    if M:
        t["Bağlı Sermaye"] = df["stok_degeri"]
    ui.tablo(t, anahtar="rp_olu", indir="olu-stok", yukseklik=420,
             kolonlar={"Bağlı Sermaye": ui.sayi_kolonu("Bağlı Sermaye", 0, True)})


def _r_devir() -> None:
    df = db.sorgu("v_stok_devir", sira="devir_hizi", tersine=True)
    if df.empty:
        st.info("Veri yok.")
        return
    df = df[(df["mevcut_stok"] > 0) | (df["satis_90g"] > 0)]
    st.info("Devir hızı = son 90 günlük satış / mevcut stok. 1'in üzeri sağlıklı, "
            "0,3'ün altı yavaş dönüş anlamına gelir.", icon="🔁")
    ui.tablo(pd.DataFrame({
        "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 40),
        "90 Gün Satış": df["satis_90g"], "Mevcut Stok": df["mevcut_stok"],
        "Devir Hızı": df["devir_hizi"],
        "Tahmini Tükenme (gün)": df["tahmini_tukenme_gun"],
    }), anahtar="rp_devir", indir="stok-devir", yukseklik=430,
        kolonlar={"Devir Hızı": ui.sayi_kolonu("Devir Hızı", 2)})


def _r_abc() -> None:
    M = auth.maliyet_gorur()
    df = db.sorgu("v_satis_karlilik",
                  select="urun_id,sku,urun_adi,marka,satir_toplam,net_kar",
                  filtreler=[("tarih", "gte", str(date.today() - timedelta(days=365)))])
    if df.empty:
        st.info("Son 12 ayda satış yok.")
        return
    g = (df.dropna(subset=["urun_id"])
           .groupby(["urun_id", "sku", "urun_adi", "marka"], as_index=False)
           .agg(ciro=("satir_toplam", "sum"), kar=("net_kar", "sum"))
           .sort_values("ciro", ascending=False))
    toplam = g["ciro"].sum() or 1
    g["kumulatif"] = (g["ciro"].cumsum() / toplam * 100).round(1)
    g["sinif"] = pd.cut(g["kumulatif"], [0, 80, 95, 100.01], labels=["A", "B", "C"])
    ui.kpi_satiri([
        {"baslik": "A Sınıfı (cironun %80'i)", "deger": str((g["sinif"] == "A").sum()),
         "alt": "", "renk": "yesil"},
        {"baslik": "B Sınıfı (%80-95)", "deger": str((g["sinif"] == "B").sum()), "alt": "",
         "renk": "sari"},
        {"baslik": "C Sınıfı (%95-100)", "deger": str((g["sinif"] == "C").sum()), "alt": "",
         "renk": "gri"},
        {"baslik": "Toplam Ciro", "deger": ui.para0(toplam), "alt": "son 12 ay", "renk": "lacivert"},
    ], sutun=4)
    t = pd.DataFrame({
        "Sınıf": g["sinif"].astype(str), "SKU": g["sku"],
        "Ürün": g["urun_adi"].str.slice(0, 40), "Marka": g["marka"], "Yıllık Ciro": g["ciro"],
    })
    if M:
        t["Net Kâr"] = g["kar"]
    t["Kümülatif %"] = g["kumulatif"]
    ui.tablo(t, anahtar="rp_abc", indir="abc-analizi", yukseklik=430, kolonlar={
        "Yıllık Ciro": ui.sayi_kolonu("Yıllık Ciro", 0, True),
        "Net Kâr": ui.sayi_kolonu("Net Kâr", 0, True),
        "Kümülatif %": ui.sayi_kolonu("Kümülatif %", 1)})


# ---------------------------------------------------------------- satış
def _satis_df(gun: int = 90) -> pd.DataFrame:
    return db.sorgu("v_satis_karlilik",
                    filtreler=[("tarih", "gte", str(date.today() - timedelta(days=gun)))])


def _r_satis() -> None:
    _satis_tablo()


def _r_karlilik() -> None:
    _satis_tablo()


def _satis_tablo() -> None:
    M = auth.maliyet_gorur()
    df = _satis_df()
    if df.empty:
        st.info("Son 90 günde satış yok.")
        return
    ciro = float(df["satir_toplam"].sum())
    kar = float(df["net_kar"].fillna(0).sum()) if M else 0
    kartlar = [
        {"baslik": "Satır Sayısı", "deger": str(len(df)), "alt": "", "renk": "lacivert"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(df["adet"].sum()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Ciro (90 gün)", "deger": ui.para0(ciro), "alt": "", "renk": "yesil"},
    ]
    if M:
        kartlar += [
            {"baslik": "Net Kâr", "deger": ui.para0(kar),
             "alt": f"%{ui.sayi_bicim(kar / ciro * 100, 1)}" if ciro else "",
             "renk": "yesil" if kar > 0 else "kirmizi"},
            {"baslik": "Toplam Komisyon", "deger": ui.para0(df["komisyon"].fillna(0).sum()),
             "alt": "", "renk": "turuncu"},
        ]
    ui.kpi_satiri(kartlar, sutun=5)

    t = pd.DataFrame({
        "Tarih": df["tarih"].apply(ui.tarih_bicim), "Sipariş": df["siparis_no"],
        "Kanal": df["kanal"], "SKU": df["sku"], "Ürün": df["urun_adi"].str.slice(0, 34),
        "Adet": df["adet"], "Tutar": df["satir_toplam"],
    })
    if M:
        t["Maliyet"] = df["maliyet"]
        t["Komisyon"] = df["komisyon"]
        t["Net Kâr"] = df["net_kar"]
        t["Marj %"] = (df["net_kar"] / df["satir_toplam"].replace(0, pd.NA) * 100).round(1)
    ui.tablo(t, anahtar="rp_satis", indir="satis", yukseklik=420, kolonlar={
        "Tutar": ui.sayi_kolonu("Tutar", 2, True), "Maliyet": ui.sayi_kolonu("Maliyet", 2, True),
        "Komisyon": ui.sayi_kolonu("Komisyon", 2, True),
        "Net Kâr": ui.sayi_kolonu("Net Kâr", 2, True), "Marj %": ui.sayi_kolonu("Marj %", 1)})


def _r_kanal() -> None:
    M = auth.maliyet_gorur()
    df = _satis_df()
    if df.empty:
        st.info("Son 90 günde satış yok.")
        return
    g = df.groupby("kanal", as_index=False).agg(
        siparis=("siparis_id", "nunique"), adet=("adet", "sum"), ciro=("satir_toplam", "sum"),
        komisyon=("komisyon", "sum"), kar=("net_kar", "sum"),
        komisyon_orani=("komisyon_orani", "first"),
    ).sort_values("ciro", ascending=False)
    g["sepet"] = g["ciro"] / g["siparis"].replace(0, pd.NA)
    g["marj"] = (g["kar"] / g["ciro"].replace(0, pd.NA) * 100).round(1)

    st.markdown("##### Kanal Ciro Dağılımı (90 gün)")
    ui.yatay_bar(g, "kanal", "ciro", "kanal", ui.renk_esle(g["kanal"]),
                 yukseklik=200, sirala=False)

    t = pd.DataFrame({
        "Kanal": g["kanal"], "Sipariş": g["siparis"], "Adet": g["adet"], "Ciro": g["ciro"],
        "Ort. Sepet": g["sepet"], "Komisyon %": g["komisyon_orani"],
    })
    if M:
        t["Komisyon ₺"] = g["komisyon"]
        t["Net Kâr"] = g["kar"]
        t["Marj %"] = g["marj"]
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "Ciro": ui.sayi_kolonu("Ciro", 0, True), "Ort. Sepet": ui.sayi_kolonu("Ort. Sepet", 0, True),
        "Komisyon ₺": ui.sayi_kolonu("Komisyon ₺", 0, True),
        "Net Kâr": ui.sayi_kolonu("Net Kâr", 0, True)})


def _r_iade() -> None:
    df = db.sorgu("iadeler", select="*, kanallar(ad), iade_satirlar(miktar, urunler(sku,ad))")
    if df.empty:
        st.info("İade kaydı yok.")
        return
    from modules.iadeler import SEBEP
    ui.kpi_satiri([
        {"baslik": "Toplam İade", "deger": str(len(df)), "alt": "", "renk": "lacivert"},
        {"baslik": "Karar Bekleyen", "deger": str((df["karar"] == "bekliyor").sum()), "alt": "",
         "renk": "turuncu"},
        {"baslik": "İmha Edilen", "deger": str((df["karar"] == "imha").sum()), "alt": "",
         "renk": "kirmizi"},
        {"baslik": "Yeniden Satılabilir",
         "deger": str((df["karar"] == "yeniden_satilabilir").sum()), "alt": "", "renk": "yesil"},
        {"baslik": "Ambalajı Açılmış", "deger": str(df["ambalaj_acik"].sum()), "alt": "",
         "renk": "gri"},
    ], sutun=5)

    sol, sag = st.columns(2, gap="medium")
    with sol:
        st.markdown("##### İade Sebepleri")
        s = df["sebep"].value_counts().reset_index()
        s.columns = ["sebep", "adet"]
        s["Sebep"] = s["sebep"].map(SEBEP).fillna(s["sebep"])
        ui.yatay_bar(s, "Sebep", "adet", yukseklik=200)
    with sag:
        st.markdown("##### En Çok İade Edilen Ürünler")
        satirlar = []
        for _, r in df.iterrows():
            for s_ in (r["iade_satirlar"] or []):
                u = s_.get("urunler") or {}
                satirlar.append({"SKU": u.get("sku"), "Ürün": u.get("ad"),
                                 "Adet": float(s_.get("miktar") or 0)})
        if satirlar:
            u = (pd.DataFrame(satirlar).groupby(["SKU", "Ürün"], as_index=False)["Adet"]
                 .sum().sort_values("Adet", ascending=False).head(15))
            st.dataframe(u, hide_index=True, width="stretch")
        else:
            st.caption("Kayıt yok")


# ---------------------------------------------------------------- tedarik
def _r_ithalat() -> None:
    if not auth.maliyet_gorur():
        st.warning("Bu rapor maliyet bilgisi içerir; görüntüleme yetkiniz yok.")
        return
    df = db.sorgu("v_ithalat_maliyet", sira="dosya_id", tersine=True)
    if df.empty:
        st.info("İthalat dosyası yok.")
        return
    adlar = {m["kod"]: m["ad"] for m in db.ref()["masraf"]}
    kalemler: dict[str, float] = {}
    for _, r in df.iterrows():
        for m in (r["masraf_detay"] or []):
            kalemler[m["kalem"]] = kalemler.get(m["kalem"], 0) + float(m["tutar_try"] or 0)
    if kalemler:
        k = pd.DataFrame([{"Kalem": adlar.get(x, x), "Tutar": v} for x, v in kalemler.items()])
        st.markdown("##### Masraf Kalemi Dağılımı (tüm dosyalar)")
        ui.yatay_bar(k.sort_values("Tutar", ascending=False), "Kalem", "Tutar", yukseklik=260)

    ui.tablo(pd.DataFrame({
        "Dosya": df["dosya_no"], "Tedarikçi": df["tedarikci"],
        "Durum": df["durum"].apply(ui.durum_etiket), "Kalem": df["kalem_sayisi"],
        "Mal Bedeli": df["mal_bedeli_try"], "Masraf": df["toplam_masraf_try"],
        "Masraf %": df["masraf_orani_yuzde"], "Landed Cost": df["toplam_landed_try"],
    }), anahtar="rp_ith", indir="ithalat-maliyet", kolonlar={
        "Mal Bedeli": ui.sayi_kolonu("Mal Bedeli", 0, True),
        "Masraf": ui.sayi_kolonu("Masraf", 0, True),
        "Masraf %": ui.sayi_kolonu("Masraf %", 1),
        "Landed Cost": ui.sayi_kolonu("Landed Cost", 0, True)})


def _r_maliyet() -> None:
    if not auth.maliyet_gorur():
        st.warning("Bu rapor maliyet bilgisi içerir; görüntüleme yetkiniz yok.")
        return
    df = db.sorgu("partiler", select="*, urunler(sku,ad), ithalat_dosyalari(dosya_no)",
                  sira="olusturuldu", tersine=True)
    if df.empty:
        st.info("Parti kaydı yok.")
        return
    st.info("Aynı ürünün farklı partilerde/ithalatlarda kaça mal olduğunu gösterir. "
            "Kur ve navlun değişimlerinin maliyete etkisi burada izlenir.", icon="📉")
    ui.tablo(pd.DataFrame({
        "SKU": df["urunler"].apply(lambda x: (x or {}).get("sku")),
        "Ürün": df["urunler"].apply(lambda x: (x or {}).get("ad") or "").str.slice(0, 36),
        "Parti": df["parti_no"], "Giriş": df["olusturuldu"].apply(ui.tarih_bicim),
        "İthalat": df["ithalat_dosyalari"].apply(lambda x: (x or {}).get("dosya_no") or "—"),
        "Döviz Maliyet": df["birim_maliyet_doviz"], "Döviz": df["doviz_kodu"].fillna("—"),
        "Kur": df["kur"], "Birim Maliyet ₺": df["birim_maliyet"],
        "Giriş Adedi": df["giris_miktari"],
    }), anahtar="rp_mal", indir="maliyet-gecmisi", yukseklik=430, kolonlar={
        "Döviz Maliyet": ui.sayi_kolonu("Döviz Maliyet", 2),
        "Kur": ui.sayi_kolonu("Kur", 2),
        "Birim Maliyet ₺": ui.sayi_kolonu("Birim Maliyet ₺", 2, True),
        "Giriş Adedi": ui.sayi_kolonu("Giriş Adedi")})
