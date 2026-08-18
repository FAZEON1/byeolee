"""Satış siparişleri — pazaryeri CSV içe aktarma, FEFO rezervasyon, sevkiyat."""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Siparişler", "pazaryeri ve manuel")
    M = auth.maliyet_gorur()

    df = db.sorgu("satis_siparisleri", select="*, kanallar(ad,kod,komisyon_orani,min_raf_omru_gun)",
                  sira="siparis_tarihi", tersine=True, limit=600)
    if df.empty:
        st.info("Sipariş yok.")
    else:
        def dur(d):
            return int((df["durum"] == d).sum())

        ui.kpi_satiri([
            {"baslik": "Yeni", "deger": str(dur("yeni")), "alt": "", "renk": "lacivert"},
            {"baslik": "Stok Rezerve", "deger": str(dur("stok_rezerve")), "alt": "", "renk": "yesil"},
            {"baslik": "Stok Bekliyor", "deger": str(dur("stok_bekliyor")), "alt": "",
             "renk": "kirmizi" if dur("stok_bekliyor") else "gri"},
            {"baslik": "Kargoda", "deger": str(dur("kargoya_verildi")), "alt": "", "renk": "gri"},
            {"baslik": "Toplam Ciro",
             "deger": ui.para0(df[df["durum"] != "iptal"]["genel_toplam"].sum()),
             "alt": "", "renk": "yesil"},
        ], sutun=5)

    if auth.yetkili("satis"):
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("⭱ Pazaryeri CSV Yükle", use_container_width=True):
            _ice_aktar()
        if c2.button("＋ Manuel Sipariş", type="primary", use_container_width=True):
            st.session_state["sip_form"] = True
        if st.session_state.get("sip_form"):
            _manuel()

    if df.empty:
        return

    c1, c2 = st.columns(2)
    durumlar = c1.multiselect("Durum", sorted(df["durum"].unique()),
                              format_func=lambda d: ui.DURUM_AD.get(d, d), key="sp_durum", placeholder="Tümü")
    kanallar = c2.multiselect(
        "Kanal", sorted(df["kanallar"].apply(lambda x: (x or {}).get("ad")).dropna().unique()),
        key="sp_kanal", placeholder="Tümü")
    f = df
    if durumlar:
        f = f[f["durum"].isin(durumlar)]
    if kanallar:
        f = f[f["kanallar"].apply(lambda x: (x or {}).get("ad")).isin(kanallar)]

    t = pd.DataFrame({
        "Sipariş No": f["siparis_no"],
        "Kanal Sip. No": f["kanal_siparis_no"],
        "Kanal": f["kanallar"].apply(lambda x: (x or {}).get("ad")),
        "Tarih": f["siparis_tarihi"].apply(ui.tarih_saat),
        "Müşteri": f["musteri_adi"],
        "İl": f["teslimat_il"],
        "Tutar": f["genel_toplam"],
    })
    if M:
        t["Komisyon"] = f["komisyon_tutari"]
    t["Durum"] = f["durum"].apply(ui.durum_etiket)
    t["Takip No"] = f["takip_no"].fillna("—")

    ui.tablo(t, anahtar="sip", indir="siparisler", yukseklik=360, kolonlar={
        "Tutar": ui.sayi_kolonu("Tutar", 2, True),
        "Komisyon": ui.sayi_kolonu("Komisyon", 2, True),
    })

    st.markdown("---")
    secenekler = {int(r.id): f"{r.siparis_no} — {r.musteri_adi or ''} — "
                             f"{ui.DURUM_AD.get(r.durum, r.durum)}" for r in f.itertuples()}
    secili = ui.secim_kutusu("Sipariş detayı", secenekler, "sp_secim", bos="— Sipariş seçin —")
    if secili:
        detay(int(secili))


def detay(siparis_id: int) -> None:
    M = auth.maliyet_gorur()
    s = db.tek("satis_siparisleri", select="*, kanallar(ad,komisyon_orani,min_raf_omru_gun)",
               filtreler=[("id", "eq", siparis_id)])
    sat = db.sorgu("satis_satirlar", select="*, urunler(sku,ad)",
                   filtreler=[("siparis_id", "eq", siparis_id)])
    pd_ = db.sorgu("sevk_parti_detay", select="*, partiler(parti_no,skt)",
                   filtreler=[("siparis_id", "eq", siparis_id)])
    if not s:
        return

    if s["durum"] == "stok_bekliyor":
        st.warning("**Stok yetersiz.** Bazı kalemler karşılanamadı — parti tahsisini kontrol edin.",
                   icon="⚠️")

    maliyet = float(sat["satir_maliyet"].fillna(0).sum()) if M and not sat.empty else 0
    komisyon = float(s.get("komisyon_tutari") or 0)
    ara = float(s.get("ara_toplam") or 0)
    net = ara - maliyet - komisyon - float(s.get("paketleme_maliyet") or 0)

    kartlar = [{"baslik": "Tutar", "deger": ui.para0(s.get("genel_toplam")), "alt": "",
                "renk": "lacivert"}]
    if M:
        kartlar += [
            {"baslik": "Maliyet", "deger": ui.para0(maliyet), "alt": "", "renk": "gri"},
            {"baslik": "Komisyon", "deger": ui.para0(komisyon),
             "alt": f"%{ui.sayi_bicim((s.get('kanallar') or {}).get('komisyon_orani'), 1)}",
             "renk": "turuncu"},
            {"baslik": "Net Kâr", "deger": ui.para0(net),
             "alt": f"%{ui.sayi_bicim(net / ara * 100, 1)}" if ara else "",
             "renk": "yesil" if net > 0 else "kirmizi"},
        ]
    else:
        kartlar += [
            {"baslik": "Kalem", "deger": str(len(sat)), "alt": "", "renk": "gri"},
            {"baslik": "Kanal", "deger": (s.get("kanallar") or {}).get("ad", "—"), "alt": "",
             "renk": "gri"},
            {"baslik": "Durum", "deger": ui.DURUM_AD.get(s["durum"], s["durum"]), "alt": "",
             "renk": "lacivert"},
        ]
    ui.kpi_satiri(kartlar, sutun=4)

    t1, t2, t3 = st.tabs(["Kalemler", f"Parti Tahsisi ({len(pd_)})", "Teslimat"])
    with t1:
        if sat.empty:
            st.info("Kalem yok.")
        else:
            g = pd.DataFrame({
                "SKU": sat.apply(lambda r: (r["urunler"] or {}).get("sku")
                                 or r["kanal_urun_kodu"] or "—", axis=1),
                "Ürün": sat.apply(lambda r: (r["urunler"] or {}).get("ad")
                                  or r["urun_adi"] or "", axis=1).str.slice(0, 40),
                "Adet": sat["adet"],
                "Birim Fiyat": sat["birim_fiyat"],
                "Tutar": sat["satir_toplam"],
            })
            if M:
                g["Maliyet"] = sat["satir_maliyet"]
                g["Kâr"] = sat["satir_kar"]
            st.dataframe(g, hide_index=True, width="stretch", column_config={
                "Adet": ui.sayi_kolonu("Adet"),
                "Birim Fiyat": ui.sayi_kolonu("Birim Fiyat", 2, True),
                "Tutar": ui.sayi_kolonu("Tutar", 2, True),
                "Maliyet": ui.sayi_kolonu("Maliyet", 2, True),
                "Kâr": ui.sayi_kolonu("Kâr", 2, True),
            })

    with t2:
        esik = (s.get("kanallar") or {}).get("min_raf_omru_gun")
        st.caption(f"⚡ FEFO kuralına göre SKT'si en yakın uygun parti seçilir."
                   + (f" Bu kanalın minimum raf ömrü eşiği: **{esik} gün**." if esik else ""))
        if pd_.empty:
            st.info("Henüz parti tahsisi yapılmadı.")
        else:
            skt = pd.to_datetime(pd_["partiler"].apply(lambda x: (x or {}).get("skt")),
                                 errors="coerce")
            kalan = (skt - pd.Timestamp.today().normalize()).dt.days
            g = pd.DataFrame({
                "Parti No": pd_["partiler"].apply(lambda x: (x or {}).get("parti_no")),
                "SKT": skt.apply(ui.tarih_bicim),
                "Kalan Gün": kalan,
                "Miktar": pd_["miktar"],
            })
            if M:
                g["Birim Maliyet"] = pd_["birim_maliyet"]
            g["Sevk"] = pd_["sevk_tarihi"].apply(
                lambda x: f"🟢 {ui.tarih_bicim(x)}" if x else "🔵 Rezerve")
            st.dataframe(g, hide_index=True, width="stretch", column_config={
                "Miktar": ui.sayi_kolonu("Miktar"),
                "Kalan Gün": ui.sayi_kolonu("Kalan Gün"),
                "Birim Maliyet": ui.sayi_kolonu("Birim Maliyet", 2, True),
            })

    with t3:
        bilgi = {
            "Kanal": (s.get("kanallar") or {}).get("ad", "—"),
            "Kanal Sipariş No": s.get("kanal_siparis_no") or "—",
            "Müşteri": s.get("musteri_adi") or "—",
            "Telefon": s.get("alici_telefon") or "—",
            "Teslimat İli": s.get("teslimat_il") or "—",
            "Teslimat Adresi": s.get("teslimat_adres") or "—",
            "Kargo": s.get("kargo_firmasi") or "—",
            "Takip No": s.get("takip_no") or "—",
            "Sevk Tarihi": ui.tarih_saat(s.get("sevk_tarihi")),
        }
        st.dataframe(pd.DataFrame({"Alan": list(bilgi), "Değer": [str(v) for v in bilgi.values()]}),
                     hide_index=True, width="stretch")

    if not auth.yetkili("satis"):
        return
    c1, c2, c3 = st.columns(3)
    if s["durum"] in ("yeni", "onaylandi", "stok_bekliyor"):
        if c1.button("⚡ Stok Rezerve Et (FEFO)", type="primary", key=f"rez_{siparis_id}",
                     use_container_width=True):
            _rezerve(siparis_id)
    if s["durum"] in ("stok_rezerve", "toplamada", "paketlendi"):
        if c2.button("🚚 Sevk Et", key=f"sevk_{siparis_id}", use_container_width=True):
            sevk_dialog(siparis_id, s)
    if s["durum"] not in ("iptal", "teslim_edildi", "kargoya_verildi"):
        if c3.button("✕ Siparişi İptal Et", key=f"ipt_{siparis_id}", use_container_width=True):
            _iptal(siparis_id)


def _rezerve(siparis_id: int) -> None:
    try:
        sonuc = db.rpc("siparis_rezerve_et", {"p_siparis_id": siparis_id})
    except Exception as e:
        st.error(f"Rezervasyon yapılamadı: {e}")
        return
    if sonuc.get("basarili"):
        st.success("Stok rezerve edildi — FEFO kuralına göre partiler tahsis edildi.")
        st.rerun()
    else:
        eks = sonuc.get("eksikler") or []
        st.warning("**Stok yetersiz.** Sipariş 'Stok Bekliyor' durumuna alındı.", icon="⚠️")
        if eks:
            st.dataframe(pd.DataFrame([{
                "Ürün": e.get("urun_adi") or f"#{e.get('urun_id')}",
                "İstenen": e.get("istenen"), "Tahsis": e.get("tahsis"), "Eksik": e.get("eksik"),
            } for e in eks]), hide_index=True, width="stretch")
        st.caption("Eksik olabilir çünkü: stok yok, parti bloke/karantinada, SKT geçmiş "
                   "veya kalan raf ömrü kanal eşiğinin altında.")


@st.dialog("Sevkiyat")
def sevk_dialog(siparis_id: int, s: dict) -> None:
    st.info("Rezerve edilen partiler stoktan düşülecek ve hareket defterine yazılacak.")
    kargo = st.text_input("Kargo Firması", value=s.get("kargo_firmasi") or "")
    takip = st.text_input("Takip No", value=s.get("takip_no") or "")
    if st.button("Sevk Et", type="primary"):
        try:
            sonuc = db.rpc("siparis_sevk_et", {
                "p_siparis_id": siparis_id, "p_kargo": kargo or None, "p_takip": takip or None})
            st.success(f"Sevk edildi: {sonuc.get('sevk_no')} · "
                       f"{sonuc.get('parti_satir')} parti hareketi")
            st.rerun()
        except Exception as e:
            st.error(f"Sevk edilemedi: {e}")


@st.dialog("Siparişi İptal Et")
def _iptal(siparis_id: int) -> None:
    st.warning("Rezerve edilen stok serbest bırakılacak (BR-13).", icon="⚠️")
    if st.button("İptal Et", type="primary"):
        try:
            db.rpc("siparis_rezerve_serbest", {"p_siparis_id": siparis_id})
            db.guncelle("satis_siparisleri", {"durum": "iptal"}, [("id", "eq", siparis_id)])
            st.success("Sipariş iptal edildi; rezerve stok serbest bırakıldı.")
            st.rerun()
        except Exception as e:
            st.error(f"İptal edilemedi: {e}")


# ---------------------------------------------------------------- manuel sipariş
@st.dialog("Manuel Sipariş", width="large")
def _manuel() -> None:
    urunler = db.sorgu("v_urun_stok", select="urun_id,sku,urun_adi,liste_fiyati,satilabilir",
                       sira="sku")
    c1, c2, c3 = st.columns(3)
    with c1:
        kanal_id = ui.secim_kutusu("Kanal *", db.ref_secim("kanal"), "sp_k", bos=None)
    with c2:
        musteri = st.text_input("Müşteri Adı *")
    with c3:
        tel = st.text_input("Telefon")
    c1, c2, c3 = st.columns(3)
    il = c1.text_input("Teslimat İli")
    kargo_bedeli = c2.number_input("Kargo Bedeli ₺", value=0.0, step=1.0)
    kanal_sip = c3.text_input("Kanal Sipariş No")
    adres = st.text_area("Teslimat Adresi", height=68)

    st.markdown("###### Kalemler")
    if "sp_satirlar" not in st.session_state:
        st.session_state["sp_satirlar"] = pd.DataFrame(
            [{"Ürün": None, "Adet": 1.0, "Birim Fiyat": 0.0}])
    secenek = [f"{r.sku} — {r.urun_adi} (stok {int(r.satilabilir or 0)})"
               for r in urunler.itertuples()]
    duzenlenen = st.data_editor(
        st.session_state["sp_satirlar"], num_rows="dynamic", width="stretch", key="sp_editor",
        column_config={
            "Ürün": st.column_config.SelectboxColumn("Ürün *", options=secenek, width="large"),
            "Adet": st.column_config.NumberColumn("Adet *", min_value=0.0, step=1.0),
            "Birim Fiyat": st.column_config.NumberColumn("Birim Fiyat ₺", step=1.0),
        })
    ara = float((duzenlenen["Adet"].fillna(0) * duzenlenen["Birim Fiyat"].fillna(0)).sum())
    st.write(f"**Ara toplam:** {ui.para(ara)}")

    c1, c2 = st.columns([1, 3])
    if c1.button("Vazgeç"):
        st.session_state.pop("sip_form", None)
        st.session_state.pop("sp_satirlar", None)
        st.rerun()
    if c2.button("Oluştur ve Rezerve Et", type="primary"):
        df = duzenlenen[duzenlenen["Ürün"].notna()]
        if not kanal_id or not musteri.strip() or df.empty:
            st.error("Kanal, müşteri adı ve en az bir kalem gerekli.")
            return
        harita = {f"{r.sku} — {r.urun_adi} (stok {int(r.satilabilir or 0)})":
                  (int(r.urun_id), r.urun_adi) for r in urunler.itertuples()}
        kanal = next((k for k in db.ref()["kanal"] if k["id"] == kanal_id), {})
        no = "SIP-M" + datetime.now().strftime("%y%m%d%H%M%S")[-8:]
        try:
            sp = db.ekle("satis_siparisleri", {
                "siparis_no": no, "kanal_id": kanal_id, "kanal_siparis_no": kanal_sip or no,
                "musteri_adi": musteri.strip(), "alici_telefon": tel or None,
                "teslimat_il": il or None, "teslimat_adres": adres or None,
                "ara_toplam": ara, "kargo_bedeli": kargo_bedeli,
                "genel_toplam": ara + kargo_bedeli,
                "komisyon_tutari": ara * float(kanal.get("komisyon_orani") or 0) / 100,
                "paketleme_maliyet": float(db.ayar("paketleme_maliyeti", 12) or 12),
                "kargo_firmasi": kanal.get("varsayilan_kargo"),
                "durum": "onaylandi", "olusturan": db.kullanici_id(),
            })[0]
            db.ekle("satis_satirlar", [{
                "siparis_id": sp["id"], "urun_id": harita[r["Ürün"]][0],
                "urun_adi": harita[r["Ürün"]][1], "adet": float(r["Adet"] or 0),
                "birim_fiyat": float(r["Birim Fiyat"] or 0),
                "satir_toplam": float(r["Adet"] or 0) * float(r["Birim Fiyat"] or 0),
            } for _, r in df.iterrows()])
            st.session_state.pop("sip_form", None)
            st.session_state.pop("sp_satirlar", None)
            sonuc = db.rpc("siparis_rezerve_et", {"p_siparis_id": sp["id"]})
            if sonuc.get("basarili"):
                st.success(f"Sipariş oluşturuldu ve stok rezerve edildi: {no}")
            else:
                st.warning(f"Sipariş oluşturuldu ({no}) ancak stok yetersiz.")
            st.rerun()
        except Exception as e:
            st.error(f"Oluşturulamadı: {e}")


# ---------------------------------------------------------------- CSV içe aktarma
@st.dialog("Pazaryeri Sipariş Yükleme", width="large")
def _ice_aktar() -> None:
    st.info("CSV dosyanızı seçin. Kolon başlıkları otomatik eşleştirilir; mükerrer siparişler "
            "(aynı kanal + kanal sipariş no) atlanır (BR-12).")
    kanal_id = ui.secim_kutusu("Kanal *", db.ref_secim("kanal"), "ia_kanal", bos=None)
    dosya = st.file_uploader("CSV dosyası", type=["csv"])
    st.caption("Beklenen kolonlar: Sipariş No · SKU/Barkod · Adet · Birim Fiyat · Müşteri · İl · Tarih")

    if not dosya or not kanal_id:
        return
    try:
        ham = dosya.getvalue().decode("utf-8-sig")
    except UnicodeDecodeError:
        ham = dosya.getvalue().decode("latin-5")
    ayirici = ";" if ham.split("\n")[0].count(";") > ham.split("\n")[0].count(",") else ","
    veri = pd.read_csv(io.StringIO(ham), sep=ayirici, dtype=str).fillna("")

    def bul(*adaylar):
        for a in adaylar:
            for k in veri.columns:
                if a in k.lower():
                    return k
        return None

    kol = {
        "no": bul("sipariş no", "siparis no", "siparis_no", "order", "sipariş numarası"),
        "sku": bul("sku", "stok kodu", "stok_kodu", "ürün kodu", "urun_kodu", "barkod"),
        "adet": bul("adet", "miktar", "quantity", "qty"),
        "fiyat": bul("birim fiyat", "fiyat", "price", "tutar"),
        "mus": bul("müşteri", "musteri", "alıcı", "alici", "customer", "ad soyad"),
        "il": bul("il", "şehir", "sehir", "city"),
        "tarih": bul("tarih", "date"),
    }
    if not kol["no"] or not kol["sku"]:
        st.error("Sipariş no ve SKU kolonları bulunamadı. Başlıkları kontrol edin.")
        st.write("Bulunan kolonlar:", list(veri.columns))
        return

    def sayiya(x):
        try:
            return float(str(x).replace("₺", "").replace(".", "").replace(",", ".").strip() or 0)
        except ValueError:
            return 0.0

    veri["_no"] = veri[kol["no"]].astype(str).str.strip()
    veri["_sku"] = veri[kol["sku"]].astype(str).str.strip()
    veri["_adet"] = veri[kol["adet"]].apply(sayiya) if kol["adet"] else 1.0
    veri["_fiyat"] = veri[kol["fiyat"]].apply(sayiya) if kol["fiyat"] else 0.0
    veri = veri[(veri["_no"] != "") & (veri["_sku"] != "")]

    st.success(f"{len(veri)} satır okundu · {veri['_no'].nunique()} benzersiz sipariş")
    st.dataframe(veri[["_no", "_sku", "_adet", "_fiyat"]].head(12).rename(columns={
        "_no": "Sipariş No", "_sku": "SKU", "_adet": "Adet", "_fiyat": "Fiyat"}),
        hide_index=True, width="stretch")

    if st.button("Yükle", type="primary"):
        _yukle(veri, kol, kanal_id, dosya.name)


def _yukle(veri: pd.DataFrame, kol: dict, kanal_id: int, dosya_adi: str) -> None:
    skular = veri["_sku"].unique().tolist()
    nolar = veri["_no"].unique().tolist()
    kanal = next((k for k in db.ref()["kanal"] if k["id"] == kanal_id), {})

    urunler = db.sorgu("urunler", select="id,sku,ad", filtreler=[("sku", "in", f"({','.join(skular)})")])
    barkod = db.sorgu("urun_barkodlar", select="urun_id,barkod",
                      filtreler=[("barkod", "in", f"({','.join(skular)})")])
    esles = db.sorgu("kanal_sku_eslesme", select="urun_id,kanal_kodu",
                     filtreler=[("kanal_id", "eq", kanal_id),
                                ("kanal_kodu", "in", f"({','.join(skular)})")])
    mevcut = db.sorgu("satis_siparisleri", select="kanal_siparis_no",
                      filtreler=[("kanal_id", "eq", kanal_id),
                                 ("kanal_siparis_no", "in", f"({','.join(nolar)})")])

    harita: dict[str, tuple] = {}
    for r in urunler.itertuples():
        harita[r.sku] = (int(r.id), r.ad)
    for r in barkod.itertuples():
        harita.setdefault(r.barkod, (int(r.urun_id), None))
    for r in esles.itertuples():
        harita.setdefault(r.kanal_kodu, (int(r.urun_id), None))
    var_olan = set(mevcut["kanal_siparis_no"]) if not mevcut.empty else set()

    eklenen = atlanan = 0
    eslesmeyen: set[str] = set()
    ilerleme = st.progress(0.0, "Yükleniyor…")
    gruplar = list(veri.groupby("_no"))

    for i, (no, grup) in enumerate(gruplar):
        ilerleme.progress((i + 1) / len(gruplar), f"{i + 1}/{len(gruplar)}")
        if no in var_olan:
            atlanan += 1
            continue
        ilk = grup.iloc[0]
        ara = float((grup["_adet"] * grup["_fiyat"]).sum())
        try:
            sp = db.ekle("satis_siparisleri", {
                "siparis_no": f"SIP-{kanal.get('kod')}-{no}", "kanal_id": kanal_id,
                "kanal_siparis_no": no,
                "musteri_adi": str(ilk[kol["mus"]]) if kol["mus"] else None,
                "teslimat_il": str(ilk[kol["il"]]) if kol["il"] else None,
                "ara_toplam": ara, "genel_toplam": ara,
                "komisyon_tutari": ara * float(kanal.get("komisyon_orani") or 0) / 100,
                "paketleme_maliyet": float(db.ayar("paketleme_maliyeti", 12) or 12),
                "kargo_firmasi": kanal.get("varsayilan_kargo"),
                "durum": "yeni", "olusturan": db.kullanici_id(),
            })[0]
            satirlar = []
            for _, k in grup.iterrows():
                u = harita.get(k["_sku"])
                if not u:
                    eslesmeyen.add(k["_sku"])
                satirlar.append({
                    "siparis_id": sp["id"], "urun_id": u[0] if u else None,
                    "kanal_urun_kodu": k["_sku"],
                    "urun_adi": (u[1] if u and u[1] else k["_sku"]),
                    "adet": k["_adet"], "birim_fiyat": k["_fiyat"],
                    "satir_toplam": k["_adet"] * k["_fiyat"],
                })
            db.ekle("satis_satirlar", satirlar)
            eklenen += 1
        except Exception:
            atlanan += 1

    db.ekle("ice_aktarimlar", {
        "tip": "siparis", "kanal_id": kanal_id, "dosya_adi": dosya_adi,
        "toplam_satir": len(veri), "basarili": eklenen, "hatali": atlanan,
        "hata_detay": {"eslesmeyen_sku": sorted(eslesmeyen)}, "kullanici": db.kullanici_id(),
    })
    ilerleme.empty()
    st.success(f"**{eklenen} sipariş** içe aktarıldı.")
    if atlanan:
        st.warning(f"{atlanan} sipariş atlandı (mükerrer — BR-12).")
    if eslesmeyen:
        st.error(f"**{len(eslesmeyen)} SKU eşleşmedi.** Bu kalemler ürüne bağlanmadı, "
                 f"stok rezerve edilemez: {', '.join(sorted(eslesmeyen)[:20])}")
    st.caption("Siparişleri 'Stok Rezerve Et' ile FEFO'ya göre partilere bağlayın.")
