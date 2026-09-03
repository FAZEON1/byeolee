"""Ürün Kartı — bir ürünle ilgili her şey tek kartta.

Düzen: üstte künye şeridi ve stok rozeti, altında hızlı arama, sonra sekmeler.
Özet sekmesinde dört KPI (stok, stok değeri, paçal maliyet, liste satış),
depo ve SKT kırılımı, en altta genel toplam ve "kaç hafta yeter" satırı.

Maliyet kaynağı `v_urun_ithalat_ozet` (gerçek landed cost, KDV hariç).
Satış kaynağı `v_kanal_satis_karlilik` (pazaryeri panel raporları).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

LOK_TIP = {
    "mal_kabul": "Mal Kabul", "ana_depo": "Ana Depo", "toplama": "Toplama",
    "karantina": "Karantina", "iade": "İade", "hasarli": "Hasarlı",
    "sevkiyat": "Sevkiyat",
}


def _guncel_kur() -> float:
    """Ayarlardaki USD/TRY kuru. Ayarlar → Genel ekranından değiştirilebilir."""
    try:
        return float(str(db.ayar("usd_kuru", 47.71)).replace(",", "."))
    except (TypeError, ValueError):
        return 47.71


def goster() -> None:
    ui.baslik("Ürün Kartı", "stok · maliyet · alım · satış")
    M = auth.maliyet_gorur()
    kur = _guncel_kur()

    kart = db.sorgu("v_urun_karti", sira="sku")
    if kart.empty:
        st.info("Katalogda ürün yok.")
        return

    secenekler = {int(r.urun_id): f"{r.sku} — {r.urun_adi}" for r in kart.itertuples()}
    secili = ui.secim_kutusu(
        "🔍 SKU / model yaz → listeden seç, kart açılır",
        secenekler, "uk_secim", bos="— Ürün seçin —")
    if not secili:
        _liste(kart, M)
        return

    u = kart[kart["urun_id"] == int(secili)].iloc[0]
    _kunye(u)

    t1, t2, t3, t4, t5 = st.tabs(
        ["📊 Özet", "🚢 Alımlar", "🧾 Satışlar", "📈 Analiz", "📦 Parti & SKT"])
    with t1:
        _ozet(u, M, kur)
    with t2:
        _alimlar(u, M)
    with t3:
        _satislar(u, M)
    with t4:
        _analiz(u, M, kur)
    with t5:
        _partiler(u)


# --------------------------------------------------------------------- künye
def _kunye(u: pd.Series) -> None:
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"### {u['sku']}")
        st.markdown(f"**{u['urun_adi']}**")
        alt = []
        if u.get("marka"):
            alt.append(f"Marka: **{u['marka']}**")
        if u.get("kategori"):
            alt.append(f"Kategori: **{u['kategori']}**")
        st.caption(" · ".join(alt) if alt else "")
    with c2:
        st.metric("Stok", ui.sayi_bicim(u["fiziksel"]))
    st.markdown("---")


# ---------------------------------------------------------------------- özet
def _dolar(v, ondalik: int = 2) -> str:
    return "—" if v is None or pd.isna(v) else f"${float(v):,.{ondalik}f}"


def _ozet(u: pd.Series, M: bool, kur: float) -> None:
    kartlar = [
        {"baslik": "Bizim Stok", "deger": ui.sayi_bicim(u["fiziksel"]),
         "alt": f"{ui.sayi_bicim(u['satilabilir'])} satılabilir", "renk": "lacivert"},
        {"baslik": "Partnerde", "deger": ui.sayi_bicim(u.get("partner_toplam_adet")),
         "alt": (f"{ui.sayi_bicim(u.get('partner_dahil_adet'))} değere dahil"
                 if (u.get("partner_toplam_adet") or 0) else "kayıt yok"),
         "renk": "turuncu" if (u.get("partner_toplam_adet") or 0) else "gri"},
    ]
    if M:
        pacal_usd = u.get("ort_birim_maliyet_usd")
        stok_usd = u.get("toplam_stok_degeri_usd")
        kartlar += [
            {"baslik": "Stok Değeri", "deger": _dolar(stok_usd, 0),
             "alt": (f"≈ {ui.para0(float(stok_usd) * kur)} · depo + Evkur"
                     if pd.notna(stok_usd) else "paçal × değerlenen stok"),
             "renk": "yesil"},
            {"baslik": "Paçal Maliyet", "deger": _dolar(pacal_usd, 4),
             "alt": (f"≈ {ui.para(float(pacal_usd) * kur)} · güncel kurla"
                     if pd.notna(pacal_usd) else "adet-ağırlıklı landed cost"),
             "renk": "kirmizi"},
        ]
    else:
        kartlar.append({"baslik": "Rezerve", "deger": ui.sayi_bicim(u["rezerve"]),
                        "alt": "siparişlere bağlı", "renk": "turuncu"})
    kartlar.append({"baslik": "Liste Satış", "deger": ui.para(u.get("liste_fiyati")),
                    "alt": "güncel", "renk": "gri"})
    ui.kpi_satiri(kartlar)

    c1, c2 = st.columns(2)
    with c1:
        _depolar(u)
    with c2:
        _partner(u)

    _skt_ozeti(u)
    _genel_toplam(u)


def _depolar(u: pd.Series) -> None:
    st.markdown("##### 🏬 Depolarımız")
    s = db.sorgu("stok", select="fiziksel_miktar,rezerve_miktar,depolar(ad),"
                                "lokasyonlar(kod,tip)",
                 filtreler=[("urun_id", "eq", int(u["urun_id"])),
                            ("fiziksel_miktar", "gt", 0)])
    if s.empty:
        st.info("Depoda fiziksel stok yok.")
        return
    s = s.copy()
    s["depo"] = s["depolar"].apply(lambda x: (x or {}).get("ad") or "—")
    s["tip"] = s["lokasyonlar"].apply(lambda x: LOK_TIP.get((x or {}).get("tip"), "—"))
    g = (s.groupby(["depo", "tip"], as_index=False)
           .agg(miktar=("fiziksel_miktar", "sum")))
    toplam = float(g["miktar"].sum()) or 1.0
    for r in g.sort_values("miktar", ascending=False).itertuples():
        a, b = st.columns([4, 1])
        a.markdown(f"**{r.depo}** · {r.tip}")
        b.markdown(f"**{ui.sayi_bicim(r.miktar)}**")
        st.progress(min(float(r.miktar) / toplam, 1.0))


def _partner(u: pd.Series) -> None:
    st.markdown("##### 🛍️ Partner Stoğu")
    d = db.sorgu("v_dis_stok_guncel",
                 select="kanal_ad,kanal_kod,stok_degerine_dahil,miktar,sube,rapor_tarihi",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))])
    if d.empty:
        st.caption("✓ Partnerlerde stok kaydı yok")
        return
    d = d.copy()
    d["miktar"] = pd.to_numeric(d["miktar"], errors="coerce").fillna(0)
    g = (d.groupby(["kanal_ad", "stok_degerine_dahil"], as_index=False)
           .agg(miktar=("miktar", "sum"), sube=("sube", "nunique")))
    toplam = float(g["miktar"].sum()) or 1.0
    for r in g.sort_values("miktar", ascending=False).itertuples():
        a, b = st.columns([4, 1])
        etiket = "değere dahil" if r.stok_degerine_dahil else "değere dahil değil"
        sube = f" · {int(r.sube)} şube" if r.sube and r.sube > 1 else ""
        a.markdown(f"**{r.kanal_ad}**")
        a.caption(f"{etiket}{sube}")
        b.markdown(f"**{ui.sayi_bicim(r.miktar)}**")
        st.progress(min(float(r.miktar) / toplam, 1.0))
    st.caption(f"Son rapor: {ui.tarih_bicim(d['rapor_tarihi'].max())}")


def _skt_ozeti(u: pd.Series) -> None:
    st.markdown("##### 📅 SKT Durumu")
    p = db.sorgu("partiler", select="parti_no,skt,giris_miktari,durum",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))], sira="skt")
    if p.empty:
        st.info("Parti kaydı yok.")
        return
    bugun = pd.Timestamp.today().normalize()
    kalan = (pd.to_datetime(p["skt"], errors="coerce") - bugun).dt.days
    st.markdown(f"🟢 **{int((kalan > 90).sum())}** parti · 90 günden uzun")
    st.markdown(f"🟡 **{int(((kalan >= 0) & (kalan <= 90)).sum())}** parti · 90 gün içinde")
    st.markdown(f"🔴 **{int((kalan < 0).sum())}** parti · süresi geçmiş")
    if pd.notna(u.get("en_yakin_skt")):
        st.caption(f"En yakın SKT: **{ui.tarih_bicim(u['en_yakin_skt'])}**")


def _genel_toplam(u: pd.Series) -> None:
    hiz = _haftalik_hiz(u)
    genel = u.get("genel_toplam_stok")
    parcalar = [f"**GENEL TOPLAM {ui.sayi_bicim(genel if pd.notna(genel) else u['fiziksel'])}**",
                f"depo {ui.sayi_bicim(u['fiziksel'])}",
                f"partner {ui.sayi_bicim(u.get('partner_toplam_adet'))}",
                f"{ui.sayi_bicim(u['rezerve'])} rezerve"]
    if hiz and hiz > 0:
        parcalar.append(
            f"~{float(u['satilabilir'] or 0) / hiz:.0f} hafta yeter "
            f"(haftada {hiz:.0f} adet)")
    st.markdown("---")
    st.markdown(" · ".join(parcalar))

    alt = []
    if pd.notna(u.get("ilk_ithalat")):
        alt.append(f"İlk alım: {ui.tarih_bicim(u['ilk_ithalat'])}")
    if pd.notna(u.get("son_ithalat")):
        alt.append(f"Son alım: {ui.tarih_bicim(u['son_ithalat'])}")
    if u.get("son_tedarikci"):
        alt.append(f"Tedarikçi: {u['son_tedarikci']}")
    if alt:
        st.caption(" · ".join(alt))

    if (u.get("yeniden_siparis_nokta") or 0) > 0 and \
       (u.get("satilabilir") or 0) <= (u.get("yeniden_siparis_nokta") or 0):
        st.warning(
            f"Satılabilir stok sipariş noktasının "
            f"({ui.sayi_bicim(u['yeniden_siparis_nokta'])}) altında.", icon="⚠️")


def _haftalik_hiz(u: pd.Series) -> float | None:
    """Son yılın satışından haftalık tüketim hızı."""
    s = db.sorgu("v_kanal_satis_karlilik",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))])
    if s.empty:
        return None
    s = s.copy()
    s["yil"] = pd.to_numeric(s["yil"], errors="coerce")
    s["net_satis_adet"] = pd.to_numeric(s["net_satis_adet"], errors="coerce")
    son = s[s["yil"] == s["yil"].max()]
    return float(son["net_satis_adet"].sum()) / 52.0 if not son.empty else None


# ------------------------------------------------------------------- alımlar
def _alimlar(u: pd.Series, M: bool) -> None:
    g = db.sorgu("v_urun_ithalat_gecmisi",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))],
                 sira="ithalat_tarihi", tersine=True)
    if g.empty:
        st.info("Bu ürün için ithalat kaydı yok.")
        return
    if M:
        st.caption(
            f"{int(u['ithalat_sayisi'] or 0)} ithalat · "
            f"{ui.sayi_bicim(u['toplam_ithal_adet'])} adet · "
            f"en düşük {_dolar(u.get('en_dusuk_birim_usd'), 4)} · "
            f"en yüksek {_dolar(u.get('en_yuksek_birim_usd'), 4)} "
            f"(ithalat kurlarıyla)")
    t = {"Tarih": g["ithalat_tarihi"], "Dosya": g["dosya_no"],
         "Tedarikçi": g["tedarikci"], "Adet": g["adet"]}
    if M:
        t.update({"Birim FOB $": g["birim_fob"],
                  "Paçal $": g["birim_landed_usd"],
                  "Paçal ₺ (o gün)": g["birim_landed_try"],
                  "Kur": g["kur"],
                  "Binen %": g["binen_masraf_orani"],
                  "Mal Bedeli ₺": g["mal_bedeli_try"],
                  "Masraf ₺": g["dagitilan_masraf_try"]})
    ui.tablo(pd.DataFrame(t), anahtar="uk_alim", indir=f"alim-{u['sku']}")


# ------------------------------------------------------------------ satışlar
def _satislar(u: pd.Series, M: bool) -> None:
    s = db.sorgu("v_kanal_satis_karlilik",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))],
                 sira="yil", tersine=True)
    if s.empty:
        st.info("Bu ürün için satış kaydı yok.")
        return
    s = s.copy()
    for a in ("net_satis_adet", "iade_adet", "net_ciro", "komisyon_tutari",
              "toplam_maliyet_try", "net_kar_try", "kar_marji", "ort_satis_fiyati"):
        s[a] = pd.to_numeric(s[a], errors="coerce")

    kartlar = [
        {"baslik": "Toplam Satış", "deger": ui.sayi_bicim(s["net_satis_adet"].sum()),
         "alt": f"{s['yil'].nunique()} yıl", "renk": "lacivert"},
        {"baslik": "Ciro", "deger": ui.para0(s["net_ciro"].sum()),
         "alt": "KDV dahil", "renk": "lacivert"},
    ]
    if M:
        kar = float(s["net_kar_try"].sum())
        kartlar += [
            {"baslik": "Komisyon", "deger": ui.para0(s["komisyon_tutari"].sum()),
             "alt": "", "renk": "kirmizi"},
            {"baslik": "Net Kâr", "deger": ui.para0(kar), "alt": "",
             "renk": "yesil" if kar > 0 else "kirmizi"},
        ]
    else:
        kartlar.append({"baslik": "İade", "deger": ui.sayi_bicim(s["iade_adet"].sum()),
                        "alt": "", "renk": "sari"})
    ui.kpi_satiri(kartlar)

    t = {"Kanal": s["kanal"], "Yıl": s["yil"].astype(str),
         "Adet": s["net_satis_adet"], "İade": s["iade_adet"],
         "Ort. Fiyat": s["ort_satis_fiyati"], "Ciro": s["net_ciro"]}
    if M:
        t.update({"Komisyon": s["komisyon_tutari"], "Maliyet": s["toplam_maliyet_try"],
                  "Net Kâr": s["net_kar_try"],
                  "Marj %": (s["kar_marji"] * 100).round(1)})
    ui.tablo(pd.DataFrame(t), anahtar="uk_satis", arama=False,
             indir=f"satis-{u['sku']}")


# -------------------------------------------------------------------- analiz
def _analiz(u: pd.Series, M: bool, kur: float) -> None:
    if not M:
        st.info("Analiz için maliyet yetkisi gerekiyor.")
        return

    satildi = float(u.get("satilan_adet") or 0)
    ithal = float(u.get("toplam_ithal_adet") or 0)
    oran = (satildi / ithal * 100) if ithal else 0
    ui.kpi_satiri([
        {"baslik": "İthal / Satış",
         "deger": f"{ui.sayi_bicim(ithal)} / {ui.sayi_bicim(satildi)}",
         "alt": f"%{oran:.0f} satıldı", "renk": "lacivert"},
        {"baslik": "Birim Marj", "deger": ui.para(u.get("birim_marj_try")),
         "alt": (f"paçal {_dolar(u.get('ort_birim_maliyet_usd'), 4)} "
                 f"≈ {ui.para(float(u['ort_birim_maliyet_usd']) * kur)}"
                 if pd.notna(u.get("ort_birim_maliyet_usd"))
                 else "ort. satış − paçal maliyet"),
         "renk": "yesil" if (u.get("birim_marj_try") or 0) > 0 else "kirmizi"},
        {"baslik": "Stok Devri", "deger": f"%{oran:.0f}",
         "alt": "ithal edilenin satılan oranı", "renk": "gri"},
        {"baslik": "Kalan Stok Değeri", "deger": _dolar(u.get("stok_degeri_usd"), 0),
         "alt": (f"≈ {ui.para0(float(u['stok_degeri_usd']) * kur)} güncel kurla"
                 if pd.notna(u.get("stok_degeri_usd")) else ""),
         "renk": "turuncu"},
    ])

    g = db.sorgu("v_urun_ithalat_gecmisi",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))],
                 sira="ithalat_tarihi")
    if len(g) > 1:
        st.caption("**Paçal maliyetin ithalattan ithalata seyri**")
        seri = g[["ithalat_tarihi", "birim_landed_try"]].copy()
        seri["ithalat_tarihi"] = pd.to_datetime(seri["ithalat_tarihi"], errors="coerce")
        seri["birim_landed_try"] = pd.to_numeric(seri["birim_landed_try"],
                                                  errors="coerce")
        seri = seri.dropna()
        if not seri.empty:
            ui.zaman_serisi(seri, "ithalat_tarihi", "birim_landed_try")

    ui.kural_notu(
        f"Paçal maliyet tüm ithalatların adet-ağırlıklı ortalamasıdır, <b>KDV hariçtir</b> "
        f"ve dolar cinsinden tutulur. TL karşılıkları <b>{kur:.2f}</b> güncel kuruyla "
        "hesaplanır (Ayarlar → <code>usd_kuru</code>). "
        "Net kâr hesabına <b>kargo, platform hizmet bedeli ve reklam gideri dahil "
        "değildir</b>."
    )


# ------------------------------------------------------------------ partiler
def _partiler(u: pd.Series) -> None:
    p = db.sorgu("partiler",
                 select="parti_no,skt,uretim_tarihi,giris_miktari,durum",
                 filtreler=[("urun_id", "eq", int(u["urun_id"]))], sira="skt")
    if p.empty:
        st.info("Parti kaydı yok.")
        return
    bugun = pd.Timestamp.today().normalize()
    skt = pd.to_datetime(p["skt"], errors="coerce")
    kalan = (skt - bugun).dt.days
    ui.tablo(pd.DataFrame({
        "Parti No": p["parti_no"],
        "SKT": skt.apply(ui.tarih_bicim),
        "Kalan Gün": kalan,
        "Giriş Miktarı": p["giris_miktari"],
        "Durum": p["durum"].apply(ui.durum_etiket),
        "Uyarı": kalan.apply(lambda k: "🔴" if pd.notna(k) and k < 0
                             else ("🟡" if pd.notna(k) and k <= 90 else "🟢")),
    }), anahtar="uk_parti", arama=False, indir=f"parti-{u['sku']}")


# --------------------------------------------------------------------- liste
def _liste(kart: pd.DataFrame, M: bool) -> None:
    st.caption(f"Ürün seçmeden genel tabloyu görüyorsunuz · {len(kart)} ürün")
    k = {"SKU": kart["sku"], "Ürün": kart["urun_adi"], "Marka": kart["marka"],
         "Depo": kart["fiziksel"], "Partner": kart["partner_toplam_adet"],
         "Genel": kart["genel_toplam_stok"], "Satılabilir": kart["satilabilir"],
         "Alım": kart["ithalat_sayisi"], "Satılan": kart["satilan_adet"]}
    if M:
        k["Paçal $"] = kart["ort_birim_maliyet_usd"]
        k["Stok Değeri $"] = kart["toplam_stok_degeri_usd"]
    ui.tablo(pd.DataFrame(k), anahtar="uk_liste", indir="urun-karti-ozet")
