"""Partner Stoğu — Evkur ve Migros haftalık stok dosyalarının yüklenmesi.

Bunlar bizim deposu değil, partnerin rafındaki mal. Bu yüzden `stok` tablosuna
yazılmaz: FEFO ve rezervasyon fonksiyonları depodaki malı sevk edilebilir kabul
eder, partner rafındaki ürünü Trendyol siparişine bağlamaya çalışır.

Her yükleme bir ANLIK GÖRÜNTÜdür; en yeni yükleme geçerli stoktur, eskiler
geçmiş olarak kalır. Ürün eşleştirmesi barkod üzerinden yapılır.

Stok değerine hangi partnerin girdiği `dis_kanal.stok_degerine_dahil` ile
belirlenir: Evkur dahil, Migros dahil değil.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

# Dosya biçimlerinin tanınacağı kolonlar
BICIM = {
    "MIGROS": {
        "barkod": "Barkod", "ad": "Satici Ürün Adi", "miktar": "Stok Miktarı",
        "tutar": "Stok Tutarı", "gunluk": "Günlük Satış Miktarı",
        "stok_gun": "Stok Gün", "sube": None, "baslik_satiri": 2, "sayfa": 0,
    },
    "EVKUR": {
        "barkod": "Stok Kodu", "ad": "Stok açıklaması", "miktar": "Envanter (Adet)",
        "tutar": None, "gunluk": "Net Adet Donemsel", "stok_gun": None,
        "sube": "Şube", "baslik_satiri": 0, "sayfa": "Sayfa1",
    },
}


def goster() -> None:
    ui.baslik("Partner Stoğu", "Evkur · Migros konsinye stok takibi")

    kanallar = db.sorgu("dis_kanal", sira="ad")
    if kanallar.empty:
        st.error("Partner tanımı yok. `26_partner_stok.sql` çalıştırıldı mı?")
        return

    t1, t2, t3 = st.tabs(["📊 Güncel Stok", "⬆️ Dosya Yükle", "🗂️ Yükleme Geçmişi"])
    with t1:
        _guncel(kanallar)
    with t2:
        if (auth.yetkili("depo") or auth.yetkili("satinalma")
                or auth.yetkili("satis")):
            _yukle(kanallar)
        else:
            st.warning("Dosya yüklemek için depo, satın alma veya satış "
                       "yetkisi gerekiyor.")
    with t3:
        _gecmis(kanallar)


# --------------------------------------------------------------- güncel stok
def _guncel(kanallar: pd.DataFrame) -> None:
    df = db.sorgu("v_dis_stok_guncel", limit=5000)
    if df.empty:
        st.info("Henüz stok dosyası yüklenmemiş. **Dosya Yükle** sekmesine geçin.")
        return
    df = df.copy()
    df["miktar"] = pd.to_numeric(df["miktar"], errors="coerce").fillna(0)
    df["tutar"] = pd.to_numeric(df["tutar"], errors="coerce")

    kartlar = []
    for r in kanallar.itertuples():
        alt = df[df["kanal_kod"] == r.kod]
        if alt.empty:
            continue
        kartlar.append({
            "baslik": r.ad,
            "deger": ui.sayi_bicim(alt["miktar"].sum()),
            "alt": (f"{alt['urun_id'].nunique()} ürün · "
                    f"{'değere dahil' if r.stok_degerine_dahil else 'değere dahil değil'}"),
            "renk": "yesil" if r.stok_degerine_dahil else "gri",
        })
    esles = df[df["urun_id"].notna()]
    kartlar.append({
        "baslik": "Eşleşmeyen", "deger": str(int(df["urun_id"].isna().sum())),
        "alt": "barkod katalogda yok",
        "renk": "kirmizi" if df["urun_id"].isna().any() else "yesil"})
    kartlar.append({
        "baslik": "Toplam Partner Stoğu", "deger": ui.sayi_bicim(df["miktar"].sum()),
        "alt": f"son rapor {ui.tarih_bicim(df['rapor_tarihi'].max())}",
        "renk": "lacivert"})
    ui.kpi_satiri(kartlar[:4])
    if len(kartlar) > 4:
        ui.kpi_satiri(kartlar[4:])

    st.markdown("---")
    secim = st.multiselect("Partner", sorted(df["kanal_ad"].unique()),
                           key="ds_f_kanal", placeholder="Tümü")
    g = df[df["kanal_ad"].isin(secim)] if secim else df

    ozet = (g.groupby(["kanal_ad", "barkod", "urun_adi"], dropna=False)
              .agg(miktar=("miktar", "sum"), tutar=("tutar", "sum"),
                   sube=("sube", "nunique"), eslesti=("urun_id", "first"))
              .reset_index().sort_values("miktar", ascending=False))
    ui.tablo(pd.DataFrame({
        "Partner": ozet["kanal_ad"],
        "Barkod": ozet["barkod"],
        "Ürün": ozet["urun_adi"].astype(str).str.slice(0, 46),
        "Adet": ozet["miktar"],
        "Şube": ozet["sube"],
        "Tutar": ozet["tutar"],
        "Katalog": ozet["eslesti"].apply(lambda x: "✅" if pd.notna(x) else "⚠️ yok"),
    }), anahtar="ds_guncel", indir="partner-stok", kolonlar={
        "Adet": ui.sayi_kolonu("Adet"),
        "Tutar": ui.sayi_kolonu("Tutar", 0, True),
    })


# ------------------------------------------------------------------- yükleme
def _yukle(kanallar: pd.DataFrame) -> None:
    secenekler = {int(r.id): f"{r.ad} ({r.kod})" for r in kanallar.itertuples()}
    kanal_id = ui.secim_kutusu("Partner *", secenekler, "ds_y_kanal",
                               bos="— Partner seçin —")
    if not kanal_id:
        st.caption("Önce hangi partnerin dosyasını yüklediğinizi seçin.")
        return
    kanal = kanallar[kanallar["id"] == int(kanal_id)].iloc[0]
    bicim = BICIM.get(kanal["kod"])
    if not bicim:
        st.error(f"'{kanal['kod']}' için dosya biçimi tanımlı değil.")
        return

    c1, c2 = st.columns([2, 1])
    dosya = c1.file_uploader(f"{kanal['ad']} stok dosyası (.xlsx)", type=["xlsx", "xls"],
                             key="ds_y_dosya")
    tarih = c2.date_input("Rapor tarihi", value=pd.Timestamp.today().date(),
                          key="ds_y_tarih", format="DD.MM.YYYY")
    if dosya is None:
        st.caption(
            "Evkur dosyasında **Sayfa1** (şube bazlı envanter), Migros dosyasında "
            "ilk sayfa okunur. Eşleştirme barkod üzerinden yapılır.")
        return

    try:
        ham = pd.read_excel(dosya, sheet_name=bicim["sayfa"],
                            header=bicim["baslik_satiri"])
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
        return

    ham.columns = [str(c).strip() for c in ham.columns]
    eksik = [a for a in (bicim["barkod"], bicim["miktar"]) if a not in ham.columns]
    if eksik:
        st.error(
            f"Beklenen kolonlar bulunamadı: {', '.join(eksik)}. "
            f"Yanlış partner seçilmiş olabilir. Dosyadaki kolonlar: "
            f"{', '.join(list(ham.columns)[:8])}…")
        return

    d = ham.dropna(subset=[bicim["barkod"]]).copy()
    d["barkod"] = (d[bicim["barkod"]].astype(str)
                   .str.replace(r"\.0$", "", regex=True).str.strip())
    d["miktar"] = pd.to_numeric(d[bicim["miktar"]], errors="coerce").fillna(0)
    d = d[d["barkod"].str.match(r"^[0-9]{8,14}$")]
    if d.empty:
        st.error("Dosyada geçerli barkodlu satır yok.")
        return

    d["urun_adi"] = d[bicim["ad"]].astype(str) if bicim["ad"] in d.columns else None
    d["sube"] = d[bicim["sube"]].astype(str) if bicim["sube"] else None
    for alan, kolon in (("tutar", bicim["tutar"]), ("gunluk_satis", bicim["gunluk"]),
                        ("stok_gun", bicim["stok_gun"])):
        d[alan] = (pd.to_numeric(d[kolon], errors="coerce")
                   if kolon and kolon in d.columns else None)

    # katalog eşleştirme
    barkodlar = sorted(set(d["barkod"]))
    kat = db.sorgu("urunler", select="id,sku,barkod_gtin",
                   filtreler=[("barkod_gtin", "in", "(" + ",".join(barkodlar) + ")")])
    harita = dict(zip(kat["barkod_gtin"], kat["id"])) if not kat.empty else {}
    d["urun_id"] = d["barkod"].map(harita)

    eslesen = int(d["urun_id"].notna().sum())
    ui.kpi_satiri([
        {"baslik": "Satır", "deger": str(len(d)), "alt": "geçerli barkodlu",
         "renk": "lacivert"},
        {"baslik": "Tekil Ürün", "deger": str(d["barkod"].nunique()), "alt": "",
         "renk": "lacivert"},
        {"baslik": "Toplam Adet", "deger": ui.sayi_bicim(d["miktar"].sum()), "alt": "",
         "renk": "yesil"},
        {"baslik": "Katalogda Yok", "deger": str(len(d) - eslesen),
         "alt": "yüklenir ama ürüne bağlanmaz",
         "renk": "kirmizi" if eslesen < len(d) else "yesil"},
    ])

    if eslesen < len(d):
        yok = sorted(set(d.loc[d["urun_id"].isna(), "barkod"]))
        st.warning(f"Katalogda olmayan barkodlar: {', '.join(yok[:12])}"
                   f"{' …' if len(yok) > 12 else ''}", icon="⚠️")

    with st.expander("Yüklenecek satırları gör", expanded=False):
        st.dataframe(d[["barkod", "urun_adi", "sube", "miktar"]].head(200),
                     hide_index=True, width="stretch")

    st.caption(f"Bu yükleme **{kanal['ad']}** için önceki anlık görüntünün yerini "
               f"alacak. Eski yükleme geçmişte kalır, silinmez.")
    if not st.button(f"⬆️ {kanal['ad']} stoğunu yükle", type="primary",
                     key="ds_y_kaydet", use_container_width=True):
        return

    try:
        bas = db.ekle("dis_stok_yukleme", {
            "dis_kanal_id": int(kanal_id),
            "rapor_tarihi": str(tarih),
            "dosya_adi": dosya.name,
            "satir_sayisi": len(d),
            "eslesen_satir": eslesen,
            "toplam_adet": float(d["miktar"].sum()),
            "toplam_tutar": (float(d["tutar"].sum())
                             if d["tutar"].notna().any() else None),
            "yukleyen": db.kullanici_id(),
        })
        if not bas:
            st.error("Yükleme kaydı oluşturulamadı.")
            return
        yukleme_id = bas[0]["id"]

        kayitlar = [{
            "yukleme_id": yukleme_id,
            "dis_kanal_id": int(kanal_id),
            "rapor_tarihi": str(tarih),
            "barkod": r.barkod,
            "urun_id": int(r.urun_id) if pd.notna(r.urun_id) else None,
            "urun_adi": (str(r.urun_adi)[:200] if pd.notna(r.urun_adi) else None),
            "sube": (str(r.sube)[:100] if pd.notna(r.sube) else None),
            "miktar": float(r.miktar),
            "tutar": float(r.tutar) if pd.notna(r.tutar) else None,
            "gunluk_satis": float(r.gunluk_satis) if pd.notna(r.gunluk_satis) else None,
            "stok_gun": float(r.stok_gun) if pd.notna(r.stok_gun) else None,
        } for r in d.itertuples()]

        for i in range(0, len(kayitlar), 500):
            db.ekle("dis_stok", kayitlar[i:i + 500])
    except Exception as e:
        st.error(f"Yüklenemedi: {e}")
        return

    db.onbellek_temizle()
    st.success(f"{kanal['ad']} · {len(d)} satır yüklendi "
               f"({ui.sayi_bicim(d['miktar'].sum())} adet).")
    st.rerun()


# -------------------------------------------------------------------- geçmiş
def _gecmis(kanallar: pd.DataFrame) -> None:
    y = db.sorgu("dis_stok_yukleme", select="*, dis_kanal(ad,kod)",
                 sira="olusturuldu", tersine=True, limit=200)
    if y.empty:
        st.info("Yükleme geçmişi yok.")
        return
    y = y.copy()
    y["partner"] = y["dis_kanal"].apply(lambda x: (x or {}).get("ad") or "—")
    ui.tablo(pd.DataFrame({
        "Rapor Tarihi": y["rapor_tarihi"],
        "Partner": y["partner"],
        "Dosya": y["dosya_adi"],
        "Satır": y["satir_sayisi"],
        "Eşleşen": y["eslesen_satir"],
        "Toplam Adet": y["toplam_adet"],
        "Yüklenme": pd.to_datetime(y["olusturuldu"], errors="coerce")
                      .dt.strftime("%d.%m.%Y %H:%M"),
    }), anahtar="ds_gecmis", indir="partner-yukleme-gecmisi", kolonlar={
        "Toplam Adet": ui.sayi_kolonu("Toplam Adet"),
    })
    ui.kural_notu(
        "Her partner için <b>en yeni rapor tarihli yükleme</b> geçerli stoktur. "
        "Yanlış dosya yüklediyseniz doğrusunu aynı tarihle tekrar yükleyin — "
        "en son eklenen kayıt geçerli olur."
    )
