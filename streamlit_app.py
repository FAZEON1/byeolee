"""KAYRAN ERP — Kozmetik stok, parti/SKT ve ithalat maliyet yönetimi.

Streamlit arayüzü. Veritabanı: Supabase (PostgreSQL + RLS).
Her kullanıcı kendi kimliğiyle bağlanır; rol bazlı maliyet maskeleme
veritabanı seviyesinde uygulanır.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="KAYRAN ERP",
    page_icon="🧴",
    layout="wide",
    initial_sidebar_state="expanded",
)

from lib import auth, db  # noqa: E402

# ---------------------------------------------------------------- stil
st.markdown(
    """
    <style>
      .block-container {padding-top:2.2rem; padding-bottom:3rem; max-width:1500px}
      [data-testid="stSidebarNav"] {padding-top:.4rem}
      section[data-testid="stSidebar"] {background:#0f172a}
      section[data-testid="stSidebar"] * {color:#cbd5e1}
      section[data-testid="stSidebar"] h1,
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3 {color:#fff}
      section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {background:#1e293b}
      div[data-testid="stMetricValue"] {font-size:1.5rem}
      .stDataFrame {border:1px solid #e2e8f0; border-radius:10px}
      hr {margin:.9rem 0}
      div[data-testid="stExpander"] {border-radius:10px}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- oturum
if not auth.oturum_acik():
    auth.giris_ekrani()
    st.stop()

from modules import (  # noqa: E402
    ayarlar, bildirimler, cariler, dashboard, denetim, hareketler, iadeler,
    ithalat, kullanicilar, malkabul, partiler, raporlar, satinalma, sayim,
    sevkiyat, siparisler, stok, urunler,
)

# ---------------------------------------------------------------- sayaçlar
@st.cache_data(ttl=60, show_spinner=False)
def _sayaclar(_kullanici: str) -> dict:
    try:
        return {
            "bildirim": db.sayi("bildirimler", [("okundu", "eq", False)]),
            "skt": db.sayi("v_skt_uyari", [("skt_renk", "in", "(kirmizi,siyah)")]),
            "siparis": db.sayi(
                "satis_siparisleri",
                [("durum", "in", "(yeni,onaylandi,stok_rezerve,stok_bekliyor,toplamada,paketlendi)")],
            ),
            "iade": db.sayi("iadeler", [("karar", "eq", "bekliyor")]),
        }
    except Exception:
        return {"bildirim": 0, "skt": 0, "siparis": 0, "iade": 0}


sayac = _sayaclar(db.kullanici_id())


def _rozet(n: int) -> str:
    return f" ({n})" if n else ""


# ---------------------------------------------------------------- kenar çubuğu
p = auth.profil()
with st.sidebar:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:11px;padding:.2rem 0 1rem">
          <div style="width:36px;height:36px;border-radius:9px;background:#1d4ed8;color:#fff;
               display:grid;place-items:center;font-weight:800;font-size:17px">K</div>
          <div><div style="color:#fff;font-weight:700;font-size:.95rem;line-height:1.1">KAYRAN ERP</div>
               <div style="color:#64748b;font-size:.62rem;letter-spacing:.7px">KOZMETİK</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- sayfalar
def _s(fn, ad, ikon, url):
    return st.Page(fn, title=ad, icon=ikon, url_path=url)


gruplar: dict[str, list] = {
    "Genel": [
        _s(dashboard.goster, "Yönetim Paneli", "📊", "panel"),
        _s(bildirimler.goster, "Bildirimler" + _rozet(sayac["bildirim"]), "🔔", "bildirimler"),
    ],
    "Ürün & Stok": [
        _s(urunler.goster, "Ürünler", "📦", "urunler"),
        _s(partiler.goster, "Parti / SKT" + _rozet(sayac["skt"]), "🕐", "partiler"),
        _s(stok.goster, "Stok Durumu", "🗂️", "stok"),
        _s(hareketler.goster, "Stok Hareketleri", "🔁", "hareketler"),
    ],
    "Tedarik": [],
    "Satış": [
        _s(siparisler.goster, "Siparişler" + _rozet(sayac["siparis"]), "🧾", "siparisler"),
        _s(iadeler.goster, "İadeler" + _rozet(sayac["iade"]), "↩️", "iadeler"),
    ],
    "Finans & Rapor": [
        _s(raporlar.goster, "Raporlar", "📈", "raporlar"),
    ],
    "Sistem": [],
}

if auth.yetkili("depo"):
    gruplar["Ürün & Stok"] += [
        _s(malkabul.goster, "Mal Kabul", "📥", "mal-kabul"),
        _s(sayim.goster, "Sayım", "✅", "sayim"),
    ]
if auth.yetkili("satinalma"):
    gruplar["Tedarik"] += [
        _s(satinalma.goster, "Satın Alma", "🛒", "satin-alma"),
        _s(ithalat.goster, "İthalat & Maliyet", "🚢", "ithalat"),
    ]
gruplar["Tedarik"].append(_s(cariler.tedarikciler, "Tedarikçiler", "🏭", "tedarikciler"))

if auth.yetkili("satis"):
    gruplar["Satış"].insert(1, _s(sevkiyat.goster, "Toplama & Sevk", "🚚", "sevkiyat"))
gruplar["Satış"].append(_s(cariler.musteriler, "Müşteriler", "👥", "musteriler"))

if auth.yetkili("finans"):
    gruplar["Finans & Rapor"].insert(0, _s(cariler.cari_hesaplar, "Cari Hesaplar", "💳", "cari"))

if auth.yetkili("sistem"):
    gruplar["Sistem"] = [
        _s(ayarlar.goster, "Ayarlar", "⚙️", "ayarlar"),
        _s(kullanicilar.goster, "Kullanıcılar", "🔑", "kullanicilar"),
        _s(denetim.goster, "Denetim İzi", "🛡️", "denetim"),
    ]

gruplar = {k: v for k, v in gruplar.items() if v}
sayfa = st.navigation(gruplar, position="sidebar", expanded=True)

# ---------------------------------------------------------------- kullanıcı kutusu
with st.sidebar:
    st.markdown("---")
    bas_harf = "".join(w[0] for w in (p.get("ad_soyad") or "?").split()[:2]).upper()
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;padding:.2rem 0 .7rem">
          <div style="width:34px;height:34px;border-radius:50%;background:#1e3a8a;color:#fff;
               display:grid;place-items:center;font-weight:700;font-size:.8rem">{bas_harf}</div>
          <div style="min-width:0">
            <div style="color:#fff;font-size:.82rem;font-weight:600;line-height:1.2;
                 overflow:hidden;text-overflow:ellipsis">{p.get('ad_soyad','')}</div>
            <div style="color:#64748b;font-size:.72rem">{auth.ROL_AD.get(auth.rol(), auth.rol())}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    if c1.button("⟳ Yenile", use_container_width=True):
        db.onbellek_temizle()
        _sayaclar.clear()
        st.rerun()
    if c2.button("⏻ Çıkış", use_container_width=True):
        auth.cikis_yap()
        st.rerun()

    if not auth.maliyet_gorur():
        st.caption("ℹ️ Rolünüz maliyet ve kâr bilgilerini görmez.")

sayfa.run()
