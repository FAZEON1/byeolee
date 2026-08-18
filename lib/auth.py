"""Oturum açma, rol ve yetki yönetimi."""
from __future__ import annotations

import streamlit as st

from lib import db

ROL_AD = {
    "sistem_yoneticisi": "Sistem Yöneticisi",
    "yonetici": "Yönetici",
    "satin_alma": "Satın Alma",
    "depo_sorumlusu": "Depo Sorumlusu",
    "depo_personeli": "Depo Personeli",
    "satis": "Satış",
    "muhasebe": "Muhasebe",
    "salt_okunur": "Salt Okunur",
}

YETKI = {
    "maliyet":   ["sistem_yoneticisi", "yonetici", "satin_alma", "muhasebe"],
    "katalog":   ["sistem_yoneticisi", "yonetici", "satin_alma"],
    "depo":      ["sistem_yoneticisi", "yonetici", "depo_sorumlusu", "depo_personeli"],
    "satinalma": ["sistem_yoneticisi", "yonetici", "satin_alma"],
    "satis":     ["sistem_yoneticisi", "yonetici", "satis", "depo_sorumlusu"],
    "finans":    ["sistem_yoneticisi", "yonetici", "muhasebe", "satin_alma"],
    "sistem":    ["sistem_yoneticisi", "yonetici"],
    "onay":      ["sistem_yoneticisi", "yonetici", "depo_sorumlusu"],
}


def rol() -> str:
    return st.session_state.get("rol", "salt_okunur")


def yetkili(anahtar: str) -> bool:
    return rol() in YETKI.get(anahtar, [])


def maliyet_gorur() -> bool:
    """Maliyet maskeleme veritabanında da uygulanır; bu yalnızca arayüz içindir."""
    return yetkili("maliyet")


def profil() -> dict:
    return st.session_state.get("profil", {})


def oturum_acik() -> bool:
    return bool(st.session_state.get("kullanici_id"))


# ---------------------------------------------------------------- giriş
def giris_yap(eposta: str, sifre: str) -> tuple[bool, str]:
    sb = db.istemci()
    try:
        sonuc = sb.auth.sign_in_with_password({"email": eposta.strip(), "password": sifre})
    except Exception as e:
        mesaj = str(e)
        if "Invalid" in mesaj or "credentials" in mesaj.lower():
            return False, "E-posta veya şifre hatalı."
        return False, mesaj

    if not sonuc.user:
        return False, "Giriş yapılamadı."

    kid = sonuc.user.id
    p = sb.table("profiller").select("*").eq("id", kid).maybe_single().execute()
    veri = p.data if p else None
    if not veri:
        sb.auth.sign_out()
        return False, "Kullanıcı profili bulunamadı. Yöneticinize başvurun."
    if not veri.get("aktif"):
        sb.auth.sign_out()
        return False, "Hesabınız pasif durumda."

    st.session_state.kullanici_id = kid
    st.session_state.profil = veri
    st.session_state.rol = veri["rol"]
    db.onbellek_temizle()

    try:
        from datetime import datetime, timezone

        sb.table("profiller").update(
            {"son_giris": datetime.now(timezone.utc).isoformat()}
        ).eq("id", kid).execute()
    except Exception:
        pass

    return True, ""


def cikis_yap() -> None:
    try:
        db.istemci().auth.sign_out()
    except Exception:
        pass
    for anahtar in ("sb", "kullanici_id", "profil", "rol"):
        st.session_state.pop(anahtar, None)
    db.onbellek_temizle()
    st.cache_data.clear()


# ---------------------------------------------------------------- giriş ekranı
def giris_ekrani() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stSidebar"], [data-testid="stSidebarNav"] {display:none}
          .block-container {padding-top:3rem; max-width:430px}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div style="text-align:center;margin-bottom:1.4rem">
          <div style="width:56px;height:56px;border-radius:15px;background:#1e3a8a;color:#fff;
               display:inline-grid;place-items:center;font-size:27px;font-weight:800">K</div>
          <h1 style="font-size:1.45rem;margin:.7rem 0 .2rem">KAYRAN ERP</h1>
          <div style="color:#64748b;font-size:.88rem">
            Kozmetik stok, parti/SKT ve ithalat maliyet yönetimi</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("giris", border=True):
        eposta = st.text_input("E-posta", placeholder="ornek@kayranerp.com")
        sifre = st.text_input("Şifre", type="password", placeholder="••••••••")
        gonder = st.form_submit_button("Giriş yap", type="primary", use_container_width=True)

    if gonder:
        if not eposta or not sifre:
            st.warning("E-posta ve şifre gerekli.")
        else:
            with st.spinner("Giriş yapılıyor…"):
                ok, hata = giris_yap(eposta, sifre)
            if ok:
                st.rerun()
            else:
                st.error(hata)

    with st.expander("Demo hesaplar"):
        st.markdown(
            """
| Rol | E-posta | Şifre |
|---|---|---|
| Sistem Yöneticisi | `admin@kayranerp.com` | `Kayran2026!` |
| Depo Sorumlusu | `depo@kayranerp.com` | `Depo2026!` |
| Satış (maliyet göremez) | `satis@kayranerp.com` | `Satis2026!` |

Maliyet maskeleme veritabanı seviyesinde çalışır — Satış rolüyle girdiğinizde
maliyet alanları arayüzde gizlenmekle kalmaz, veritabanından da boş döner.
"""
        )
