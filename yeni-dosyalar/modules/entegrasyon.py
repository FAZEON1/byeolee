"""Pazaryeri entegrasyonu — senkron günlüğü, eşleşmeyen ürünler, gönderim önizleme.

Senkronizasyonu GitHub Actions üzerindeki işçi (entegrasyon/senkron.py) yapar.
Bu ekran yalnızca sonucu izler ve eşleşmeyen ürünleri düzeltmenizi sağlar.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

ISLEM_AD = {
    "siparis_cek": "Sipariş çekme",
    "stok_gonder": "Stok gönderme",
    "durum_gonder": "Durum bildirimi",
    "siparis_cek_kuru": "Sipariş çekme (kuru deneme)",
}


SIRA = ["TY", "HB", "N11", "AMZ"]


def _kanal_secimi() -> dict | None:
    kanallar = sorted(
        (k for k in db.ref().get("kanal", []) if k["kod"] in SIRA),
        key=lambda k: SIRA.index(k["kod"]))
    if not kanallar:
        st.warning("Tanımlı pazaryeri kanalı yok.")
        return None
    secim = st.selectbox(
        "Kanal", kanallar, key="ent_kanal",
        format_func=lambda k: f"{k['ad']} ({k['kod']})")
    return secim


def _son_calisma(kanal_id: int) -> pd.DataFrame:
    return db.sorgu(
        "entegrasyon_log", "*",
        [("kanal_id", "eq", kanal_id)], sira="baslangic", tersine=True, limit=200)


def _kpi(gunluk: pd.DataFrame, kanal_id: int) -> None:
    def son(islem: str) -> str:
        if gunluk.empty:
            return "—"
        alt = gunluk[gunluk["islem"] == islem]
        if alt.empty:
            return "—"
        satir = alt.iloc[0]
        return ui.tarih_saat(satir["baslangic"]) + ("" if satir["basarili"] else " ⚠")

    bekleyen = db.sayi("v_kanal_bildirim_bekleyen", [("kanal_id", "eq", kanal_id)])
    hatali = 0 if gunluk.empty else int((~gunluk["basarili"].astype(bool)).sum())

    ui.kpi_satiri([
        {"baslik": "Son sipariş çekme", "deger": son("siparis_cek"),
         "alt": "Trendyol → ERP", "renk": "lacivert"},
        {"baslik": "Son stok gönderme", "deger": son("stok_gonder"),
         "alt": "ERP → Trendyol", "renk": "koyu"},
        {"baslik": "Bildirim bekleyen", "deger": str(bekleyen),
         "alt": "paket durumu gönderilecek", "renk": "turuncu"},
        {"baslik": "Son 200 kayıtta hata", "deger": str(hatali),
         "alt": "başarısız çalışma", "renk": "kirmizi" if hatali else "yesil"},
    ])


# ---------------------------------------------------------------- sekmeler
def _sekme_gunluk(gunluk: pd.DataFrame) -> None:
    if gunluk.empty:
        st.info("Henüz senkronizasyon çalışmamış. GitHub Actions'ta iş akışını "
                "elle bir kez çalıştırın (Run workflow).")
        return
    df = gunluk.copy()
    df["İşlem"] = df["islem"].map(ISLEM_AD).fillna(df["islem"])
    df["Başlangıç"] = df["baslangic"].map(ui.tarih_saat)
    df["Sonuç"] = df["basarili"].map(lambda x: "✅ Başarılı" if x else "❌ Hata")
    df["Hata"] = df["hata_mesaji"].fillna("")
    gorunum = df[["Başlangıç", "İşlem", "Sonuç", "okunan", "yazilan",
                  "atlanan", "hatali", "Hata"]].rename(columns={
        "okunan": "Okunan", "yazilan": "Yazılan",
        "atlanan": "Atlanan", "hatali": "Hatalı"})
    ui.tablo(gorunum, anahtar="ent_log", indir="entegrasyon-gunlugu", yukseklik=430)

    with st.expander("Son çalışmanın ayrıntısı"):
        st.json(gunluk.iloc[0].get("detay") or {})


def _sekme_eslesmeyen(kanal: dict) -> None:
    ui.kural_notu(
        "Pazaryerinden gelen bir satır ürünle eşleşemediyse sipariş <b>rezerve edilmez</b>. "
        "Eşleştirmeyi burada tanımlayın; bir sonraki senkronda otomatik çalışır. "
        "Kalıcı çözüm: Trendyol'daki ürünün barkodunu ERP'deki GTIN ile aynı yapmak."
    )
    sb = db.istemci()
    try:
        y = (sb.table("satis_satirlar")
             .select("id,kanal_urun_kodu,urun_adi,adet,siparis_id,"
                     "satis_siparisleri!inner(kanal_id,siparis_no,kanal_siparis_no)")
             .is_("urun_id", "null")
             .eq("satis_siparisleri.kanal_id", kanal["id"])
             .limit(300).execute())
        satirlar = y.data or []
    except Exception as e:
        st.error(f"Sorgu hatası: {e}")
        return

    if not satirlar:
        st.success("Eşleşmeyen satır yok. Tüm pazaryeri satırları bir ürüne bağlı.")
        return

    df = pd.DataFrame([{
        "Sipariş": (s.get("satis_siparisleri") or {}).get("siparis_no"),
        "Pazaryeri kodu": s.get("kanal_urun_kodu"),
        "Ürün adı (pazaryeri)": s.get("urun_adi"),
        "Adet": s.get("adet"),
    } for s in satirlar])
    ui.tablo(df, anahtar="ent_esl", indir="eslesmeyen-satirlar")

    kodlar = sorted({s.get("kanal_urun_kodu") for s in satirlar if s.get("kanal_urun_kodu")})
    if not kodlar or not auth.yetkili("katalog"):
        if kodlar:
            st.caption("Eşleştirme tanımlamak için katalog yetkisi gerekir.")
        return

    st.markdown("##### Eşleştirme tanımla")
    urunler = db.sorgu("urunler", "id,sku,ad,barkod_gtin",
                       [("durum", "eq", "aktif")], sira="ad", limit=5000)
    if urunler.empty:
        return
    secenek = {int(r.id): f"{r.sku} · {r.ad}" for r in urunler.itertuples()}

    with st.form("ent_eslestir"):
        c1, c2 = st.columns(2)
        kod = c1.selectbox("Pazaryeri kodu / barkodu", kodlar)
        urun_id = c2.selectbox("ERP ürünü", list(secenek),
                               format_func=lambda i: secenek[i])
        gonder = st.form_submit_button("Eşleştir", type="primary")
    if gonder:
        try:
            db.ekle("kanal_sku_eslesme", {
                "kanal_id": kanal["id"], "kanal_kodu": kod, "urun_id": int(urun_id)})
            st.success(f"{kod} → {secenek[int(urun_id)]} eşleştirildi. "
                       "Bu satırlar bir sonraki senkronda otomatik bağlanmaz; "
                       "mevcut siparişi Siparişler ekranından yeniden rezerve edin.")
            st.rerun()
        except Exception as e:
            st.error(f"Eşleştirme eklenemedi: {e}")


def _sekme_stok(kanal: dict) -> None:
    ui.kural_notu(
        f"Gönderilecek miktar = satılabilir stok − rezerve. "
        f"SKT'si geçmiş, bloke ve kanal asgari raf ömrünün "
        f"(<b>{kanal.get('min_raf_omru_gun', 0)} gün</b>) altındaki partiler "
        f"<b>hariç tutulur</b>; ayrıca %{kanal.get('stok_rezerv_yuzde', 0)} güvenlik payı düşülür."
    )
    try:
        veri = db.rpc("kanal_gonderilecek_stok", {"p_kanal_id": kanal["id"]}) or []
    except Exception as e:
        st.error(f"Hesaplanamadı: {e}")
        return
    if not veri:
        st.info("Gönderilecek stok bulunamadı.")
        return
    df = pd.DataFrame(veri)
    barkodsuz = int(df["barkod"].isna().sum()) if "barkod" in df else 0
    if barkodsuz:
        st.warning(f"{barkodsuz} ürünün barkodu (GTIN) yok — bunlar gönderilemez. "
                   "Ürünler ekranından barkod girin.")
    df = df.rename(columns={"sku": "SKU", "barkod": "Barkod",
                            "gonderilecek": "Gönderilecek",
                            "liste_fiyati": "Liste fiyatı",
                            "satis_fiyati": "Satış fiyatı"})
    ui.tablo(df.drop(columns=["urun_id"], errors="ignore"),
             kolonlar={"Gönderilecek": ui.sayi_kolonu("Gönderilecek"),
                       "Liste fiyatı": ui.sayi_kolonu("Liste fiyatı", 2, True),
                       "Satış fiyatı": ui.sayi_kolonu("Satış fiyatı", 2, True)},
             anahtar="ent_stok", indir="gonderilecek-stok", yukseklik=430)


def _sekme_bildirim(kanal: dict) -> None:
    ui.kural_notu(
        "ERP'de toplamaya alınan sipariş Trendyol'da <b>Picking</b>, paketlenen/kargoya "
        "verilen sipariş <b>Invoiced</b> yapılır. Bu bildirimi de GitHub Actions işçisi gönderir."
    )
    df = db.sorgu("v_kanal_bildirim_bekleyen", "*", [("kanal_id", "eq", kanal["id"])])
    if df.empty:
        st.success("Bildirim bekleyen sipariş yok.")
        return
    g = pd.DataFrame({
        "Sipariş": df["siparis_no"],
        "Pazaryeri no": df["kanal_siparis_no"],
        "Paket": df["kanal_paket_id"],
        "ERP durumu": df["durum"],
        "Bildirilen": df["kanal_bildirim_durumu"].fillna("—"),
        "Takip no": df["takip_no"].fillna(""),
    })
    ui.tablo(g, anahtar="ent_bildirim", indir="bildirim-bekleyen")


# ---------------------------------------------------------------- sayfa
def goster() -> None:
    ui.baslik("Pazaryeri Entegrasyonu", "Trendyol · sipariş, stok ve durum senkronizasyonu")
    kanal = _kanal_secimi()
    if not kanal:
        return
    gunluk = _son_calisma(kanal["id"])
    _kpi(gunluk, kanal["id"])
    st.markdown("---")

    s1, s2, s3, s4 = st.tabs(
        ["📜 Senkron günlüğü", "🔗 Eşleşmeyen ürünler",
         "📤 Gönderilecek stok", "📣 Bildirim bekleyenler"])
    with s1:
        _sekme_gunluk(gunluk)
    with s2:
        _sekme_eslesmeyen(kanal)
    with s3:
        _sekme_stok(kanal)
    with s4:
        _sekme_bildirim(kanal)
