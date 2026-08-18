"""Parti / SKT takibi — sistemin kalbi. FEFO, raf ömrü, bloke, imha, geri çağırma."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

BANTLAR = [
    ("siyah", "SKT Geçmiş", "siyah"),
    ("kirmizi", "Kritik ≤30g", "kirmizi"),
    ("turuncu", "Aksiyon 31-90g", "turuncu"),
    ("sari", "İzle 91-180g", "sari"),
    ("yesil", "Güvenli 180g+", "yesil"),
]


def goster() -> None:
    ui.baslik("Parti / SKT Takibi", "FEFO ve raf ömrü yönetimi")
    _gc_rapor()
    M = auth.maliyet_gorur()

    df = db.sorgu("v_parti_stok", sira="skt")
    if df.empty:
        st.info("Henüz parti kaydı yok.")
        return

    # ---------------------------------------------------------------- özet
    kartlar = []
    for kod, ad, renk in BANTLAR:
        g = df[(df["skt_renk"] == kod) & (df["fiziksel"] > 0)]
        deger = float(g["stok_degeri"].fillna(0).sum()) if M and "stok_degeri" in g else 0
        kartlar.append({
            "baslik": f"{ui.SKT_NOKTA[kod]} {ad}",
            "deger": ui.sayi_bicim(len(g)),
            "alt": f"{ui.sayi_bicim(g['fiziksel'].sum())} adet"
                   + (f" · {ui.para0(deger)}" if M else ""),
            "renk": renk if len(g) else "gri",
        })
    ui.kpi_satiri(kartlar, sutun=5)

    ui.kural_notu(
        "⚙️ <b>FEFO aktif.</b> Sevkiyatta her zaman SKT'si en yakın uygun parti önerilir. "
        "Kanal bazlı minimum raf ömrü eşiğinin altındaki partiler otomatik satışa kapatılır; "
        "SKT'si geçmiş parti hiçbir koşulda sevk edilemez (BR-04, BR-05)."
    )

    # ---------------------------------------------------------------- filtre
    c1, c2, c3 = st.columns([2, 2, 2])
    bant = c1.multiselect(
        "SKT bandı", [b[0] for b in BANTLAR],
        format_func=lambda k: f"{ui.SKT_NOKTA[k]} {dict((b[0], b[1]) for b in BANTLAR)[k]}",
        key="pt_bant", placeholder="Tümü",
    )
    durumlar = sorted(df["durum"].dropna().unique())
    durum = c2.multiselect("Parti durumu", durumlar,
                           format_func=lambda d: ui.DURUM_AD.get(d, d), key="pt_durum", placeholder="Tümü")
    sadece_stok = c3.checkbox("Sadece stokta olanlar", value=True, key="pt_stok")

    f = df
    if bant:
        f = f[f["skt_renk"].isin(bant)]
    if durum:
        f = f[f["durum"].isin(durum)]
    if sadece_stok:
        f = f[f["fiziksel"] > 0]

    # ---------------------------------------------------------------- tablo
    gosterim = pd.DataFrame({
        "SKU": f["sku"],
        "Ürün": f["urun_adi"].str.slice(0, 42),
        "Parti No": f["parti_no"],
        "SKT": f["skt"].apply(ui.tarih_bicim),
        "Durum (SKT)": f.apply(lambda r: ui.skt_etiket(r["skt_renk"], r["kalan_gun"]), axis=1),
        "Parti Durumu": f["durum"].apply(ui.durum_etiket),
        "Fiziksel": f["fiziksel"],
        "Rezerve": f["rezerve"],
        "Satılabilir": f["satilabilir"],
    })
    if M:
        gosterim["Birim Maliyet"] = f["birim_maliyet"]
        gosterim["Stok Değeri"] = f["stok_degeri"]

    ui.tablo(
        gosterim, anahtar="partiler", indir="partiler", yukseklik=430,
        kolonlar={
            "Fiziksel": ui.sayi_kolonu("Fiziksel"),
            "Rezerve": ui.sayi_kolonu("Rezerve"),
            "Satılabilir": ui.sayi_kolonu("Satılabilir"),
            "Birim Maliyet": ui.sayi_kolonu("Birim Maliyet", 2, True),
            "Stok Değeri": ui.sayi_kolonu("Stok Değeri", 0, True),
        },
    )

    # ---------------------------------------------------------------- detay
    st.markdown("---")
    st.markdown("##### Parti Detayı ve İşlemler")
    secenekler = {
        int(r.parti_id): f"{r.parti_no} — {r.sku} — SKT {ui.tarih_bicim(r.skt)}"
        for r in f.itertuples()
    }
    if not secenekler:
        return
    secili = ui.secim_kutusu("Parti seçin", secenekler, "pt_secim", bos="— Parti seçin —")
    if secili:
        _detay(int(secili))


# ---------------------------------------------------------------- detay
def _detay(parti_id: int) -> None:
    M = auth.maliyet_gorur()
    p = db.tek("v_parti_stok", filtreler=[("parti_id", "eq", parti_id)])
    ham = db.tek("partiler", filtreler=[("id", "eq", parti_id)])
    if not p:
        st.warning("Parti bulunamadı.")
        return

    if p["skt_renk"] == "siyah":
        st.error("**Bu partinin son kullanma tarihi geçmiş.** Sistem sevkiyatı teknik olarak "
                 "engeller (BR-05). İmha veya tedarikçi iadesi gerekiyor.", icon="⚠️")
    elif p["skt_renk"] == "kirmizi":
        st.warning(f"**SKT'ye {int(p['kalan_gun'])} gün kaldı.** İndirim, kampanya/set yapma "
                   "veya iade seçeneklerini değerlendirin.", icon="⏰")
    if p["durum"] == "bloke":
        st.error(f"**Parti bloke.** Sebep: {ham.get('blokaj_sebebi') or '—'}", icon="⛔")
    if p["durum"] == "geri_cagrildi":
        st.error(f"**Bu parti geri çağrıldı.** Sebep: {ham.get('blokaj_sebebi') or '—'}", icon="🚨")

    kartlar = [
        {"baslik": "Fiziksel", "deger": ui.sayi_bicim(p["fiziksel"]), "alt": "", "renk": "lacivert"},
        {"baslik": "Satılabilir", "deger": ui.sayi_bicim(p["satilabilir"]), "alt": "",
         "renk": "yesil" if p["satilabilir"] else "gri"},
        {"baslik": "Rezerve", "deger": ui.sayi_bicim(p["rezerve"]), "alt": "", "renk": "gri"},
        {"baslik": "Stok Değeri" if M else "Giriş Miktarı",
         "deger": ui.para0(p["stok_degeri"]) if M else ui.sayi_bicim(ham.get("giris_miktari")),
         "alt": "", "renk": "lacivert"},
    ]
    ui.kpi_satiri(kartlar, sutun=4)

    t1, t2, t3, t4 = st.tabs(["Bilgiler", "Lokasyonlar", "Hareketler", "İzlenebilirlik"])

    with t1:
        bilgi = {
            "Ürün": f"{p['sku']} — {p['urun_adi']}",
            "Parti No": p["parti_no"],
            "Üretim Tarihi": ui.tarih_bicim(p["uretim_tarihi"]),
            "Son Kullanma Tarihi": f"{ui.tarih_bicim(p['skt'])} · "
                                   f"{ui.skt_etiket(p['skt_renk'], p['kalan_gun'])}",
            "Parti Durumu": ui.durum_etiket(p["durum"]),
            "Giriş Miktarı": ui.sayi_bicim(ham.get("giris_miktari")),
            "Tedarikçi": db.ref_secim("tedarikci", "unvan").get(p.get("tedarikci_id"), "—"),
        }
        if M:
            dvz = ""
            if ham.get("birim_maliyet_doviz"):
                dvz = (f"  ({ui.sayi_bicim(ham['birim_maliyet_doviz'], 2)} "
                       f"{ham.get('doviz_kodu')} × {ui.sayi_bicim(ham.get('kur'), 2)})")
            bilgi["Birim Maliyet"] = ui.para(p["birim_maliyet"]) + dvz
        bilgi["Notlar"] = ham.get("notlar") or "—"
        st.dataframe(
            pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
            hide_index=True, width="stretch",
        )

    with t2:
        lok = db.sorgu(
            "stok", select="*, lokasyonlar(kod,ad,tip), depolar(ad)",
            filtreler=[("parti_id", "eq", parti_id), ("fiziksel_miktar", "gt", 0)],
        )
        if lok.empty:
            st.info("Bu parti stokta değil.")
        else:
            st.dataframe(
                pd.DataFrame({
                    "Depo": lok["depolar"].apply(lambda x: (x or {}).get("ad")),
                    "Lokasyon": lok["lokasyonlar"].apply(lambda x: (x or {}).get("kod")),
                    "Fiziksel": lok["fiziksel_miktar"],
                    "Rezerve": lok["rezerve_miktar"],
                }), hide_index=True, width="stretch",
            )

    with t3:
        hrk = db.sorgu("stok_hareket", filtreler=[("parti_id", "eq", parti_id)],
                       sira="tarih", tersine=True, limit=60)
        if hrk.empty:
            st.info("Hareket yok.")
        else:
            st.dataframe(
                pd.DataFrame({
                    "Tarih": hrk["tarih"].apply(ui.tarih_saat),
                    "Hareket": hrk["tip"].map(ui.HAREKET_AD).fillna(hrk["tip"]),
                    "Miktar": hrk["miktar"],
                    "FEFO dışı": hrk["fefo_istisna"].apply(lambda x: "⚠️" if x else ""),
                    "Açıklama": hrk["aciklama"],
                }), hide_index=True, width="stretch",
            )

    with t4:
        st.caption("Bu parti hangi siparişlerle kime gitti? Geri çağırmada ulaşılacak liste budur.")
        izle = db.sorgu("v_parti_izlenebilirlik", filtreler=[("parti_id", "eq", parti_id)])
        izle = izle[izle["siparis_no"].notna()] if not izle.empty else izle
        if izle.empty:
            st.info("Bu partiden henüz sevkiyat yapılmamış.")
        else:
            st.dataframe(
                pd.DataFrame({
                    "Sipariş": izle["siparis_no"],
                    "Kanal": izle["kanal"],
                    "Tarih": izle["siparis_tarihi"].apply(ui.tarih_bicim),
                    "Müşteri": izle["musteri"],
                    "Telefon": izle["alici_telefon"],
                    "Adet": izle["sevk_miktar"],
                    "Durum": izle["siparis_durum"].apply(ui.durum_etiket),
                }), hide_index=True, width="stretch",
            )

    # ---------------------------------------------------------------- işlemler
    if not (auth.yetkili("depo") or auth.yetkili("sistem")):
        return
    st.markdown("###### İşlemler")
    c1, c2, c3, c4 = st.columns(4)

    if auth.yetkili("depo"):
        if p["durum"] == "kullanilabilir" and c1.button("⛔ Bloke Et", key="pt_bloke",
                                                        use_container_width=True):
            _bloke(parti_id)
        if p["durum"] in ("bloke", "karantina") and c1.button(
                "✓ Kullanıma Aç", key="pt_ac", type="primary", use_container_width=True):
            db.guncelle("partiler", {"durum": "kullanilabilir", "blokaj_sebebi": None},
                        [("id", "eq", parti_id)])
            st.success("Parti kullanıma açıldı.")
            st.rerun()
        if p["fiziksel"] > 0 and c2.button("🗑 İmha Et", key="pt_imha", use_container_width=True):
            _imha(parti_id)
    if c3.button("🚨 Geri Çağır", key="pt_gc", use_container_width=True):
        _geri_cagir(parti_id, p)


@st.dialog("Partiyi Bloke Et")
def _bloke(parti_id: int) -> None:
    st.warning("Bloke edilen parti hiçbir sevkiyata konu olamaz.", icon="⚠️")
    sebep = st.text_area("Blokaj sebebi *",
                         placeholder="Örn: Tedarikçi kalite şikâyeti, ambalaj hasarı…")
    if st.button("Bloke Et", type="primary"):
        if not sebep.strip():
            st.error("Blokaj sebebi zorunludur.")
            return
        db.guncelle("partiler", {"durum": "bloke", "blokaj_sebebi": sebep.strip()},
                    [("id", "eq", parti_id)])
        st.success("Parti bloke edildi.")
        st.rerun()


@st.dialog("İmha Kaydı")
def _imha(parti_id: int) -> None:
    st.warning("İmha edilen stok geri alınamaz; düzeltme ancak ters kayıtla yapılır.", icon="⚠️")
    lok = db.sorgu("stok", select="*, lokasyonlar(kod)",
                   filtreler=[("parti_id", "eq", parti_id), ("fiziksel_miktar", "gt", 0)])
    if lok.empty:
        st.info("Bu parti stokta değil.")
        return
    secenekler = {
        int(r.lokasyon_id): f"{(r.lokasyonlar or {}).get('kod')} — "
                            f"{ui.sayi_bicim(r.fiziksel_miktar)} adet"
        for r in lok.itertuples()
    }
    lok_id = ui.secim_kutusu("Lokasyon *", secenekler, "im_lok", bos=None)
    enb = float(lok[lok["lokasyon_id"] == lok_id]["fiziksel_miktar"].iloc[0]) if lok_id else 0.0
    miktar = st.number_input("İmha miktarı *", min_value=0.0, max_value=enb, value=enb, step=1.0)
    sebep = st.selectbox("Sebep *", ["SKT geçti", "Ambalaj hasarı", "Kalite sorunu",
                                     "Geri çağırma", "Diğer"])
    if st.button("İmha Et", type="primary"):
        if miktar <= 0:
            st.error("Miktar sıfırdan büyük olmalıdır.")
            return
        sonuc = db.rpc("parti_imha_et", {
            "p_parti_id": parti_id, "p_lokasyon_id": lok_id,
            "p_miktar": miktar, "p_sebep": sebep,
        })
        st.success(f"İmha kaydedildi · zarar {ui.para(sonuc.get('zarar_try'))}")
        st.rerun()


@st.dialog("🚨 Geri Çağırma Başlat", width="large")
def _geri_cagir(parti_id: int, p: dict) -> None:
    st.error(
        "Geri çağırma başlatıldığında partinin kalan tüm stoğu **otomatik bloke edilir (BR-15)** "
        "ve bu partiden sevkiyat yapılan tüm müşteriler listelenir.", icon="⚠️",
    )
    st.write(f"**Parti:** {p['parti_no']} · **Ürün:** {p['sku']} — {p['urun_adi']} · "
             f"**Kalan stok:** {ui.sayi_bicim(p['fiziksel'])} adet")
    sebep = st.text_area("Geri çağırma sebebi *",
                         placeholder="Örn: Üretici tarafından bildirilen kontaminasyon riski")
    if st.button("Geri Çağırmayı Başlat", type="primary"):
        if not sebep.strip():
            st.error("Sebep zorunludur.")
            return
        sonuc = db.rpc("geri_cagirma_baslat", {"p_parti_id": parti_id, "p_sebep": sebep.strip()})
        st.session_state["gc_sonuc"] = sonuc
        st.rerun()


def _gc_rapor() -> None:
    sonuc = st.session_state.pop("gc_sonuc", None)
    if not sonuc:
        return
    st.error("**Geri çağırma başlatıldı.** Kalan stok bloke edildi.", icon="🚨")
    sip = sonuc.get("siparisler") or []
    stk = sonuc.get("kalan_stok") or []
    st.markdown(f"###### Ulaşılması gereken müşteriler ({len(sip)})")
    if sip:
        st.dataframe(pd.DataFrame(sip), hide_index=True, width="stretch")
    else:
        st.info("Bu partiden sevkiyat yapılmamış.")
    st.markdown("###### Depoda bloke edilen stok")
    st.dataframe(pd.DataFrame(stk) if stk else pd.DataFrame([{"bilgi": "Depoda kalan stok yok"}]),
                 hide_index=True, width="stretch")
