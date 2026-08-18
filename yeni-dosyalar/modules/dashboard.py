"""Yönetim paneli — anlık durum özeti."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui


def goster() -> None:
    ui.baslik("Yönetim Paneli", "anlık durum")
    M = auth.maliyet_gorur()

    d = db.tek("v_dashboard") or {}
    skt = db.sorgu("v_skt_uyari", filtreler=[("fiziksel", "gt", 0)], sira="skt", limit=500)
    kritik = db.sorgu("v_kritik_stok", limit=10)
    satis = db.sorgu(
        "v_satis_karlilik",
        select="tarih,satir_toplam,net_kar,kanal,marka,sku,urun_adi,adet",
        filtreler=[("tarih", "gte", str(date.today() - timedelta(days=30)))],
    )
    olu = db.sorgu(
        "v_olu_stok", filtreler=[("hareketsiz_gun", "gte", 120)],
        sira="stok_degeri", tersine=True, limit=5,
    )

    def g(anahtar, vars=0):
        v = d.get(anahtar)
        return vars if v is None or pd.isna(v) else v

    # ---------------------------------------------------------------- uyarı
    if g("skt_gecmis_tutari") and M:
        gecmis = len(skt[skt["skt_renk"] == "siyah"]) if not skt.empty else 0
        st.error(
            f"**{gecmis} partide SKT geçmiş stok var — {ui.para0(g('skt_gecmis_tutari'))} değerinde.** "
            "Bu stok satılabilir değil; imha kararı veya tedarikçi iadesi gerekiyor.",
            icon="⚠️",
        )

    # ---------------------------------------------------------------- KPI
    kartlar = [
        {"baslik": "Toplam Stok Değeri",
         "deger": ui.para0(d.get("toplam_stok_degeri")) if M else "•••",
         "alt": f"{ui.sayi_bicim(g('toplam_adet'))} adet · {ui.sayi_bicim(g('aktif_urun'))} aktif ürün",
         "renk": "lacivert"},
        {"baslik": "SKT Uyarısı", "deger": ui.sayi_bicim(g("skt_uyari_parti")),
         "alt": f"parti · {ui.para0(d.get('skt_risk_tutari')) if M else '•••'} risk altında",
         "renk": "turuncu" if g("skt_uyari_parti") else "gri"},
        {"baslik": "Kritik Stok", "deger": ui.sayi_bicim(g("kritik_stok_adet")),
         "alt": "ürün sipariş noktasının altında",
         "renk": "kirmizi" if g("kritik_stok_adet") else "yesil"},
        {"baslik": "Bekleyen Sipariş", "deger": ui.sayi_bicim(g("bekleyen_siparis")),
         "alt": (f"{ui.sayi_bicim(g('stok_bekleyen_siparis'))} tanesi stok bekliyor"
                 if g("stok_bekleyen_siparis") else "tümü karşılanabilir"),
         "renk": "lacivert"},
        {"baslik": "Bu Ay Ciro", "deger": ui.para0(g("ay_ciro")),
         "alt": f"bugün {ui.para0(g('bugun_ciro'))}", "renk": "yesil"},
    ]
    if M:
        kartlar.append({"baslik": "Bu Ay Net Kâr", "deger": ui.para0(d.get("ay_net_kar")),
                        "alt": "komisyon sonrası", "renk": "yesil"})
    kartlar += [
        {"baslik": "Yoldaki İthalat", "deger": ui.sayi_bicim(g("yoldaki_ithalat")),
         "alt": f"{ui.sayi_bicim(g('acik_satin_alma'))} açık satın alma", "renk": "gri"},
        {"baslik": "Bekleyen İade", "deger": ui.sayi_bicim(g("bekleyen_iade")),
         "alt": "kalite kararı bekliyor",
         "renk": "turuncu" if g("bekleyen_iade") else "gri"},
    ]
    ui.kpi_satiri(kartlar, sutun=4)

    # ---------------------------------------------------------------- grafikler
    sol, sag = st.columns(2, gap="medium")

    with sol:
        st.markdown("##### Stok Raf Ömrü Dağılımı")
        if skt.empty:
            st.caption("Stokta SKT'li parti yok")
        else:
            bantlar = [
                ("siyah", "SKT geçmiş"), ("kirmizi", "≤30 gün"), ("turuncu", "31-90 gün"),
                ("sari", "91-180 gün"), ("yesil", "180+ gün"),
            ]
            satirlar = []
            for k, ad in bantlar:
                grup = skt[skt["skt_renk"] == k]
                if grup.empty:
                    continue
                satirlar.append({
                    "Band": f"{ui.SKT_NOKTA[k]} {ad}",
                    "Parti": len(grup),
                    "Adet": int(grup["fiziksel"].sum()),
                    "Değer": float(grup["risk_tutari"].sum()) if M and "risk_tutari" in grup else 0.0,
                    "renk": k,
                })
            bdf = pd.DataFrame(satirlar)
            if not bdf.empty:
                ui.yatay_bar(
                    bdf, "Band", "Değer" if M else "Adet", "Band",
                    {r["Band"]: ui.RENK[r["renk"]] for r in satirlar},
                    yukseklik=210, sirala=False,
                )
                st.caption(
                    ("Bar uzunluğu stok değerini gösterir. " if M else "")
                    + f"Toplam {ui.sayi_bicim(skt['fiziksel'].sum())} adet stok izleniyor."
                )

    with sag:
        st.markdown("##### Son 30 Gün Ciro")
        if satis.empty:
            st.caption("Son 30 günde satış yok")
        else:
            s = satis.copy()
            s["tarih"] = pd.to_datetime(s["tarih"])
            gunluk = s.groupby("tarih", as_index=False)["satir_toplam"].sum()
            ui.zaman_serisi(gunluk, "tarih", "satir_toplam", yukseklik=170)
            st.markdown("##### Kanal Dağılımı")
            kanal = (
                s.groupby("kanal", as_index=False)["satir_toplam"]
                .sum().sort_values("satir_toplam", ascending=False)
            )
            ui.yatay_bar(kanal, "kanal", "satir_toplam", "kanal",
                         ui.renk_esle(kanal["kanal"]), yukseklik=150, sirala=False)

    # ---------------------------------------------------------------- listeler
    st.write("")
    sol2, sag2 = st.columns(2, gap="medium")

    with sol2:
        st.markdown("##### SKT'si En Yakın Partiler")
        if skt.empty:
            st.caption("Kayıt yok")
        else:
            t = skt.head(8).copy()
            g_df = pd.DataFrame({
                "SKU": t["sku"],
                "Ürün": t["urun_adi"].str.slice(0, 34),
                "Parti": t["parti_no"],
                "SKT": t.apply(lambda r: ui.skt_etiket(r["skt_renk"], r["kalan_gun"]), axis=1),
                "Stok": t["fiziksel"],
            })
            if M and "risk_tutari" in t:
                g_df["Değer"] = t["risk_tutari"]
            st.dataframe(g_df, hide_index=True, width="stretch",
                         column_config={"Değer": ui.sayi_kolonu("Değer", 0, True)})

    with sag2:
        st.markdown("##### Sipariş Verilmesi Gerekenler")
        if kritik.empty:
            st.success("Kritik stokta ürün yok 👍")
        else:
            k = kritik.head(10)
            st.dataframe(
                pd.DataFrame({
                    "SKU": k["sku"],
                    "Ürün": k["urun_adi"].str.slice(0, 32),
                    "Satılabilir": k["satilabilir"],
                    "Sip. Noktası": k["yeniden_siparis_nokta"],
                    "Eksik": k["eksik_adet"].clip(lower=0),
                }),
                hide_index=True, width="stretch",
            )
        if not olu.empty and M:
            st.markdown("##### En Değerli Ölü Stok")
            st.dataframe(
                pd.DataFrame({
                    "SKU": olu["sku"],
                    "Adet": olu["fiziksel"],
                    "Hareketsiz": olu["hareketsiz_gun"].apply(
                        lambda x: "hiç satılmadı" if x > 9000 else f"{int(x)} gün"),
                    "Değer": olu["stok_degeri"],
                }),
                hide_index=True, width="stretch",
                column_config={"Değer": ui.sayi_kolonu("Değer", 0, True)},
            )
