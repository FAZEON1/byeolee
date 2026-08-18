"""Ortak arayüz bileşenleri: biçimlendirme, KPI kartları, tablolar, grafikler."""
from __future__ import annotations

from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------- renk paleti
RENK = {
    "lacivert": "#1d4ed8",
    "koyu": "#1e3a8a",
    "yesil": "#16a34a",
    "sari": "#ca8a04",
    "turuncu": "#ea580c",
    "kirmizi": "#dc2626",
    "siyah": "#1f2937",
    "gri": "#94a3b8",
}
KANAL_RENK = ["#1d4ed8", "#0891b2", "#7c3aed", "#c2410c", "#15803d", "#be123c", "#a16207"]

SKT_NOKTA = {
    "yesil": "🟢", "sari": "🟡", "turuncu": "🟠",
    "kirmizi": "🔴", "siyah": "⚫", "bilinmiyor": "⚪",
}
SKT_AD = {
    "yesil": "Güvenli", "sari": "İzle", "turuncu": "Aksiyon al",
    "kirmizi": "Kritik", "siyah": "SKT GEÇTİ", "bilinmiyor": "SKT yok",
}

DURUM_AD = {
    "karantina": "Karantina", "kullanilabilir": "Kullanılabilir", "bloke": "Bloke",
    "skt_gecmis": "SKT Geçmiş", "hasarli": "Hasarlı", "imha_edildi": "İmha Edildi",
    "tedarikciye_iade": "Tedarikçiye İade", "geri_cagrildi": "Geri Çağrıldı",
    "taslak": "Taslak", "onay_bekliyor": "Onay Bekliyor", "onaylandi": "Onaylandı",
    "kismen_teslim": "Kısmen Teslim", "teslim_edildi": "Teslim Edildi", "iptal": "İptal",
    "acik": "Açık", "siparis_verildi": "Sipariş Verildi", "yolda": "Yolda",
    "gumrukte": "Gümrükte", "gumrukten_cekildi": "Gümrükten Çekildi",
    "depoya_alindi": "Depoya Alındı", "kapandi": "Kapandı",
    "yeni": "Yeni", "stok_rezerve": "Stok Rezerve", "stok_bekliyor": "Stok Bekliyor",
    "toplamada": "Toplamada", "paketlendi": "Paketlendi",
    "kargoya_verildi": "Kargoya Verildi", "iade": "İade",
    "bekliyor": "Bekliyor", "yeniden_satilabilir": "Yeniden Satılabilir", "imha": "İmha",
    "sayiliyor": "Sayılıyor", "tamamlandi": "Tamamlandı",
    "aktif": "Aktif", "pasif": "Pasif", "askida": "Askıda",
}
DURUM_IKON = {
    "kullanilabilir": "🟢", "onaylandi": "🟢", "teslim_edildi": "🟢", "depoya_alindi": "🟢",
    "tamamlandi": "🟢", "yeniden_satilabilir": "🟢", "kargoya_verildi": "🟢", "aktif": "🟢",
    "karantina": "🟡", "onay_bekliyor": "🟡", "kismen_teslim": "🟡", "yolda": "🟡",
    "bekliyor": "🟡", "sayiliyor": "🟡",
    "gumrukte": "🟠", "stok_bekliyor": "🟠",
    "bloke": "🔴", "hasarli": "🔴", "geri_cagrildi": "🔴", "imha": "🔴",
    "skt_gecmis": "⚫", "imha_edildi": "⚫",
    "iptal": "⚪", "taslak": "⚪", "kapandi": "⚪", "pasif": "⚪",
    "yeni": "🔵", "stok_rezerve": "🔵", "acik": "🔵", "siparis_verildi": "🔵",
    "toplamada": "🔵", "paketlendi": "🔵",
}

HAREKET_AD = {
    "acilis": "Açılış", "mal_kabul": "Mal Kabul", "satis_cikis": "Satış",
    "iade_giris": "İade", "tedarikciye_iade": "Ted. İade",
    "depo_ici_transfer": "Transfer", "depolar_arasi_transfer": "Depo Transfer",
    "sayim_fazla": "Sayım +", "sayim_eksik": "Sayım −", "imha": "İmha", "fire": "Fire",
    "numune_cikis": "Numune", "set_yapma": "Set Yapma", "set_bozma": "Set Bozma",
    "duzeltme": "Düzeltme",
}

DAGITIM_AD = {
    "mal_bedeli": "Mal bedeline göre", "adet": "Adete göre", "agirlik": "Ağırlığa göre",
    "hacim": "Hacme göre", "esit": "Eşit dağıtım", "dogrudan": "Doğrudan",
}


# ---------------------------------------------------------------- biçimlendirme
def para(v, kurus: bool = True) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{v:,.2f}" if kurus else f"{v:,.0f}"
    return "₺" + s.replace(",", "␣").replace(".", ",").replace("␣", ".")


def para0(v) -> str:
    return para(v, kurus=False)


def sayi_bicim(v, ondalik: int = 0) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{v:,.{ondalik}f}"
    return s.replace(",", "␣").replace(".", ",").replace("␣", ".")


def tarih_bicim(d) -> str:
    if d is None or (isinstance(d, float) and pd.isna(d)) or d == "":
        return "—"
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d.replace("Z", "+00:00"))
        except ValueError:
            return d
    if isinstance(d, (datetime, date)):
        return d.strftime("%d.%m.%Y")
    return str(d)


def tarih_saat(d) -> str:
    if d is None or (isinstance(d, float) and pd.isna(d)) or d == "":
        return "—"
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d.replace("Z", "+00:00"))
        except ValueError:
            return d
    return d.strftime("%d.%m.%y %H:%M") if isinstance(d, datetime) else str(d)


def skt_etiket(renk: str | None, gun=None) -> str:
    if not renk:
        return "—"
    ad = SKT_AD.get(renk, renk)
    if gun is None or pd.isna(gun) or renk == "bilinmiyor":
        return f"{SKT_NOKTA.get(renk, '⚪')} {ad}"
    gun = int(gun)
    ek = f"{abs(gun)} gün önce" if gun < 0 else f"{gun} gün"
    return f"{SKT_NOKTA.get(renk, '⚪')} {ad} · {ek}"


def durum_etiket(d) -> str:
    if not d or (isinstance(d, float) and pd.isna(d)):
        return "—"
    return f"{DURUM_IKON.get(d, '⚪')} {DURUM_AD.get(d, d)}"


# ---------------------------------------------------------------- KPI kartları
def _kart_html(baslik: str, deger: str, alt: str, renk: str) -> str:
    return f"""
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;
                box-shadow:0 1px 3px rgba(15,23,42,.08);border-left:3px solid {renk};height:100%">
      <div style="font-size:.68rem;color:#475569;font-weight:600;text-transform:uppercase;
                  letter-spacing:.4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{baslik}</div>
      <div style="font-size:1.45rem;font-weight:800;margin-top:4px;letter-spacing:-.5px;
                  color:#0f172a;line-height:1.15">{deger}</div>
      <div style="font-size:.72rem;color:#94a3b8;margin-top:2px">{alt}</div>
    </div>"""


def kpi_satiri(kartlar: list[dict], sutun: int = 4) -> None:
    """kartlar: [{'baslik':..,'deger':..,'alt':..,'renk':'lacivert'}]"""
    for i in range(0, len(kartlar), sutun):
        cols = st.columns(sutun, gap="small")
        for c, k in zip(cols, kartlar[i : i + sutun]):
            with c:
                st.markdown(
                    _kart_html(
                        k.get("baslik", ""),
                        k.get("deger", "—"),
                        k.get("alt", ""),
                        RENK.get(k.get("renk", "lacivert"), RENK["lacivert"]),
                    ),
                    unsafe_allow_html=True,
                )
        st.write("")


def baslik(metin: str, alt: str = "") -> None:
    st.markdown(
        f"""<div style="margin-bottom:.8rem">
        <span style="font-size:1.35rem;font-weight:700;letter-spacing:-.3px">{metin}</span>
        <span style="font-size:.85rem;color:#94a3b8;margin-left:.5rem">{alt}</span></div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- tablo
def tablo(
    df: pd.DataFrame,
    kolonlar: dict | None = None,
    yukseklik: int | None = None,
    arama: bool = True,
    anahtar: str = "tbl",
    indir: str | None = None,
) -> pd.DataFrame:
    """Aranabilir, biçimli tablo. Filtrelenmiş DataFrame'i döndürür."""
    if df is None or df.empty:
        st.info("Kayıt bulunamadı.")
        return pd.DataFrame()

    gosterim = df
    if arama:
        c1, c2 = st.columns([3, 1])
        q = c1.text_input(
            "Ara", key=f"{anahtar}_ara", label_visibility="collapsed",
            placeholder="Ara…"
        )
        if q:
            maske = df.astype(str).apply(
                lambda s: s.str.lower().str.contains(q.lower(), na=False)
            ).any(axis=1)
            gosterim = df[maske]
        c2.markdown(
            f"<div style='text-align:right;padding-top:.45rem;color:#64748b;font-size:.85rem'>"
            f"{sayi_bicim(len(gosterim))} kayıt</div>",
            unsafe_allow_html=True,
        )

    st.dataframe(
        gosterim,
        width="stretch",
        hide_index=True,
        height=yukseklik,
        column_config=kolonlar or {},
    )

    if indir and not gosterim.empty:
        st.download_button(
            "⭳ CSV indir",
            gosterim.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"{indir}-{date.today()}.csv",
            mime="text/csv",
            key=f"{anahtar}_csv",
        )
    return gosterim


def sayi_kolonu(baslik_: str, ondalik: int = 0, para_mi: bool = False):
    """Binlik ayraçlı sayı kolonu. Para kolonlarında başlığa ₺ eklenir
    (Streamlit'in yerelleştirilmiş biçimi para simgesi almıyor)."""
    if para_mi:
        return st.column_config.NumberColumn(f"{baslik_} ₺", format="localized")
    if ondalik:
        return st.column_config.NumberColumn(baslik_, format=f"%.{ondalik}f")
    return st.column_config.NumberColumn(baslik_, format="localized")


# ---------------------------------------------------------------- grafikler
def renk_esle(degerler, palet: list[str] | None = None) -> dict:
    """Sıralı değer listesini palete eşler — grafik renkleri deterministik olsun diye."""
    palet = palet or KANAL_RENK
    return {d: palet[i % len(palet)] for i, d in enumerate(list(degerler))}


def yatay_bar(
    df: pd.DataFrame, etiket: str, deger: str, renk_alan: str | None = None,
    renkler: dict | list[str] | None = None, yukseklik: int = 240, baslik_: str = "",
    sirala: bool = True,
) -> None:
    """Yatay bar grafiği. `renkler` sözlük verilirse {değer: renk} olarak eşlenir —
    Altair'in alfabetik sıraya göre renk atamasını engeller."""
    if df is None or df.empty:
        st.caption("Veri yok")
        return
    sira = "-x" if sirala else list(df[etiket])
    kodlama = {
        "x": alt.X(f"{deger}:Q", title=None, axis=alt.Axis(format="~s", grid=True)),
        "y": alt.Y(f"{etiket}:N", title=None, sort=sira),
        "tooltip": [c for c in df.columns if not c.startswith("_")],
    }
    if renk_alan:
        if isinstance(renkler, dict):
            olcek = alt.Scale(domain=list(renkler), range=list(renkler.values()))
        else:
            olcek = alt.Scale(domain=list(df[renk_alan]),
                              range=(renkler or KANAL_RENK)[: len(df)])
        kodlama["color"] = alt.Color(f"{renk_alan}:N", legend=None, scale=olcek)
        temel = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18)
    else:
        temel = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18, color=RENK["lacivert"])
    st.altair_chart(
        temel.encode(**kodlama).properties(height=yukseklik, title=baslik_),
        use_container_width=True,
    )


def zaman_serisi(df: pd.DataFrame, x: str, y: str, yukseklik: int = 220) -> None:
    if df.empty:
        st.caption("Veri yok")
        return
    st.altair_chart(
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3, color=RENK["lacivert"])
        .encode(
            x=alt.X(f"{x}:T", title=None),
            y=alt.Y(f"{y}:Q", title=None, axis=alt.Axis(format="~s")),
            tooltip=[x, y],
        )
        .properties(height=yukseklik),
        use_container_width=True,
    )


# ---------------------------------------------------------------- bilgi kutuları
def kural_notu(metin: str) -> None:
    st.markdown(
        f"""<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
             padding:10px 13px;font-size:.85rem;color:#475569;margin-bottom:.9rem">{metin}</div>""",
        unsafe_allow_html=True,
    )


def secim_kutusu(etiket: str, secimler: dict, anahtar: str, bos: str | None = "— Seçiniz —",
                 varsayilan=None):
    """{id: ad} sözlüğünden selectbox — seçilen id'yi döndürür."""
    ogeler = list(secimler.items())
    if bos:
        ogeler = [(None, bos)] + ogeler
    idx = 0
    if varsayilan is not None:
        for i, (k, _) in enumerate(ogeler):
            if k == varsayilan:
                idx = i
                break
    secim = st.selectbox(
        etiket, ogeler, index=idx, key=anahtar, format_func=lambda x: x[1]
    )
    return secim[0] if secim else None
