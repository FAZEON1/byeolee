"""ÜTS (Ürün Takip Sistemi) bildirim takibi.

Kozmetik ürünlerin Sağlık Bakanlığı ÜTS'ye bildirilmesi zorunludur; bildirimi
ürünü piyasaya arz eden (üretici veya **ithalatçı**) yapar. Bu ekran hangi
ürünün bildirim numarasının girildiğini takip eder ve eksikleri listeler.

Sorgulama ÜTS portalından yapılır (oturum ve doğrulama gerektirdiği için
uygulama içinden otomatik sorgulanamaz):
https://utsuygulama.saglik.gov.tr/UTS/vatandas
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import auth, db, ui

UTS_PORTAL = "https://utsuygulama.saglik.gov.tr/UTS/vatandas"
TITCK = "https://www.titck.gov.tr/faaliyetalanlari/kozmetik/urun-takip-sistemi"


def _veri() -> pd.DataFrame:
    df = db.sorgu(
        "urunler",
        select="id,sku,ad,barkod_gtin,bildirim_no,durum,urun_tipi,marka_id,mensei_ulke",
        sira="sku")
    if df.empty:
        return df
    for alan in ("bildirim_no", "barkod_gtin", "urun_tipi", "mensei_ulke"):
        if alan not in df.columns:
            df[alan] = None
    markalar = {m["id"]: m["ad"] for m in db.ref().get("marka", [])}
    df["marka"] = df["marka_id"].map(markalar).fillna("—")
    df["bildirim_no"] = df["bildirim_no"].fillna("")
    return df


def goster() -> None:
    ui.baslik("ÜTS Takibi", "Sağlık Bakanlığı Ürün Takip Sistemi bildirimleri")

    ui.kural_notu(
        "Kozmetik ürünün ÜTS bildirimi <b>piyasaya arz eden</b> tarafından yapılır — "
        "ürünü siz ithal ediyorsanız yükümlülük sizdedir, yurt içinden alıyorsanız "
        "ithalatçıdadır. Bildirimi olmayan ürünün satışı mevzuata aykırıdır ve "
        "pazaryerleri bu ürünleri kapatabilir.<br>"
        f"Sorgulama: <a href='{UTS_PORTAL}' target='_blank'>ÜTS Vatandaş Sorgu Ekranı</a> · "
        f"<a href='{TITCK}' target='_blank'>TİTCK kozmetik ÜTS sayfası</a>"
    )

    df = _veri()
    if df.empty:
        st.info("Katalogda ürün yok.")
        return

    aktif = df[df["durum"] == "aktif"]
    barkodlu = aktif[aktif["barkod_gtin"].notna() & (aktif["barkod_gtin"] != "")]
    girilmis = barkodlu[barkodlu["bildirim_no"] != ""]
    eksik = barkodlu[barkodlu["bildirim_no"] == ""]
    barkodsuz = aktif[aktif["barkod_gtin"].isna() | (aktif["barkod_gtin"] == "")]

    ui.kpi_satiri([
        {"baslik": "Aktif ürün", "deger": str(len(aktif)), "alt": "katalogda", "renk": "lacivert"},
        {"baslik": "ÜTS no girilmiş", "deger": str(len(girilmis)),
         "alt": "bildirimi doğrulanmış", "renk": "yesil"},
        {"baslik": "ÜTS no eksik", "deger": str(len(eksik)),
         "alt": "sorgulanacak", "renk": "kirmizi" if len(eksik) else "yesil"},
        {"baslik": "Barkodsuz ürün", "deger": str(len(barkodsuz)),
         "alt": "set / aksesuar · sorgulanamaz", "renk": "gri"},
    ])
    st.markdown("---")

    s1, s2, s3 = st.tabs(["🔎 Eksikler", "✅ Girilmiş olanlar", "⚙️ Barkodsuz ürünler"])

    with s1:
        if eksik.empty:
            st.success("Barkodu olan tüm aktif ürünlerin ÜTS bildirim numarası girilmiş.")
        else:
            st.caption(
                "Barkodu ÜTS portalında aratıp çıkan **bildirim numarasını** aşağıdaki "
                "sütuna yazın ve **Kaydet**'e basın. Ürün ÜTS'de hiç çıkmıyorsa "
                "`BULUNAMADI` yazın — böylece hangi ürünlerin kaydı eksik olduğu listede kalır."
            )
            _duzenle(eksik, "uts_eksik")

    with s2:
        if girilmis.empty:
            st.info("Henüz ÜTS numarası girilmiş ürün yok.")
        else:
            _duzenle(girilmis, "uts_dolu")

    with s3:
        if barkodsuz.empty:
            st.success("Barkodsuz aktif ürün yok.")
        else:
            st.caption("Bu ürünlerin GTIN barkodu yok (set, kit, aksesuar veya eksik veri). "
                       "ÜTS sorgusu barkodla yapıldığı için önce barkod girilmeli.")
            ui.tablo(pd.DataFrame({
                "SKU": barkodsuz["sku"], "Ürün": barkodsuz["ad"],
                "Marka": barkodsuz["marka"], "Tip": barkodsuz["urun_tipi"],
            }), anahtar="uts_barkodsuz", indir="uts-barkodsuz")


def _duzenle(df: pd.DataFrame, anahtar: str) -> None:
    tablo = pd.DataFrame({
        "id": df["id"],
        "SKU": df["sku"],
        "Ürün": df["ad"],
        "Marka": df["marka"],
        "Barkod": df["barkod_gtin"],
        "ÜTS Bildirim No": df["bildirim_no"],
    })
    yetki = auth.yetkili("katalog")

    q = st.text_input("Ara", key=f"{anahtar}_ara", label_visibility="collapsed",
                      placeholder="SKU, ürün adı veya barkod…")
    gosterim = tablo
    if q:
        maske = tablo.astype(str).apply(
            lambda s: s.str.lower().str.contains(q.lower(), na=False)).any(axis=1)
        gosterim = tablo[maske]

    yeni = st.data_editor(
        gosterim, hide_index=True, width="stretch", height=430,
        key=f"{anahtar}_editor",
        disabled=([] if yetki else ["ÜTS Bildirim No"]) + ["id", "SKU", "Ürün", "Marka", "Barkod"],
        column_config={
            "id": None,
            "Barkod": st.column_config.TextColumn("Barkod", help="ÜTS'de bu numarayı aratın"),
            "ÜTS Bildirim No": st.column_config.TextColumn(
                "ÜTS Bildirim No", help="Bulunamadıysa BULUNAMADI yazın"),
        })

    c1, c2 = st.columns([1, 3])
    if yetki and c1.button("Kaydet", type="primary", key=f"{anahtar}_kaydet"):
        eski = {int(k): (v or "").strip()
                for k, v in gosterim.set_index("id")["ÜTS Bildirim No"].items()}
        degisen = {}
        for kayit in yeni.to_dict("records"):
            uid = int(kayit["id"])
            deger = (kayit.get("ÜTS Bildirim No") or "").strip()
            if deger != eski.get(uid, ""):
                degisen[uid] = deger
        if not degisen:
            st.info("Değişiklik yok.")
        else:
            hata = 0
            for uid, deger in degisen.items():
                try:
                    db.guncelle("urunler", {"bildirim_no": deger or None}, [("id", "eq", uid)])
                except Exception as e:
                    hata += 1
                    st.error(f"{uid}: {e}")
            if hata == 0:
                st.success(f"{len(degisen)} ürün güncellendi.")
                st.rerun()
    c2.download_button(
        "⭳ CSV indir", gosterim.drop(columns=["id"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="uts-listesi.csv", mime="text/csv", key=f"{anahtar}_csv")
