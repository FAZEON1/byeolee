"""Oturum açma, rol ve yetki yönetimi.

Kullanıcılar e-posta değil **kullanıcı adı** ile girer (örn. `hakan`).
Uygulama arka planda bunu `hakan@<alan-adı>` adresine çevirip Supabase Auth'a sorar;
böylece kullanıcı e-posta görmez ama veritabanındaki RLS ve maliyet maskeleme
olduğu gibi çalışmaya devam eder.
"""
from __future__ import annotations

import streamlit as st

from lib import db

# Kullanıcı adının arkasına eklenen alan adı.
# secrets.toml içinde KULLANICI_ALAN_ADI ile değiştirilebilir.
VARSAYILAN_ALAN = "kayranerp.com"

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

# Supabase'in varsayılan asgari şifre uzunluğu
ASGARI_SIFRE = 6


def alan_adi() -> str:
    return db._ayar("KULLANICI_ALAN_ADI", VARSAYILAN_ALAN) or VARSAYILAN_ALAN


def kullanici_adindan_eposta(girdi: str) -> str:
    """`hakan` -> `hakan@kayranerp.com`. Zaten e-posta girilmişse dokunmaz."""
    g = (girdi or "").strip().lower()
    return g if "@" in g else f"{g}@{alan_adi()}"


def kullanici_adi() -> str:
    return (profil().get("eposta") or "").split("@")[0]


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
def giris_yap(girdi: str, sifre: str) -> tuple[bool, str]:
    sb = db.istemci()
    eposta = kullanici_adindan_eposta(girdi)
    try:
        sonuc = sb.auth.sign_in_with_password({"email": eposta, "password": sifre})
    except Exception as e:
        mesaj = str(e)
        if "Invalid" in mesaj or "credentials" in mesaj.lower():
            return False, "Kullanıcı adı veya şifre hatalı."
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
        return False, "Hesabınız pasif durumda. Yöneticinize başvurun."

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


# ---------------------------------------------------------------- şifre değiştirme
def sifre_degistir(yeni: str, yeni_tekrar: str) -> tuple[bool, str]:
    if yeni != yeni_tekrar:
        return False, "İki şifre birbiriyle aynı değil."
    if len(yeni) < ASGARI_SIFRE:
        return False, f"Şifre en az {ASGARI_SIFRE} karakter olmalıdır."
    try:
        db.istemci().auth.update_user({"password": yeni})
    except Exception as e:
        mesaj = str(e)
        if "should be at least" in mesaj or "Password" in mesaj:
            return False, f"Şifre en az {ASGARI_SIFRE} karakter olmalıdır."
        if "same_password" in mesaj or "different from the old" in mesaj:
            return False, "Yeni şifre eskisiyle aynı olamaz."
        return False, mesaj
    return True, ""


@st.dialog("Şifre Değiştir")
def sifre_degistir_penceresi() -> None:
    st.caption(f"Kullanıcı: **{kullanici_adi()}** · {profil().get('ad_soyad','')}")
    with st.form("sifre_form"):
        yeni = st.text_input("Yeni şifre", type="password",
                             help=f"En az {ASGARI_SIFRE} karakter")
        tekrar = st.text_input("Yeni şifre (tekrar)", type="password")
        gonder = st.form_submit_button("Şifreyi Değiştir", type="primary")
    if gonder:
        ok, hata = sifre_degistir(yeni, tekrar)
        if ok:
            st.success("Şifreniz değiştirildi. Bir sonraki girişte yenisini kullanın.")
        else:
            st.error(hata)


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
        ad = st.text_input("Kullanıcı adı", placeholder="örn. hakan")
        sifre = st.text_input("Şifre", type="password", placeholder="••••••••")
        gonder = st.form_submit_button("Giriş yap", type="primary", use_container_width=True)

    if gonder:
        if not ad or not sifre:
            st.warning("Kullanıcı adı ve şifre gerekli.")
        else:
            with st.spinner("Giriş yapılıyor…"):
                ok, hata = giris_yap(ad, sifre)
            if ok:
                st.rerun()
            else:
                st.error(hata)

    st.caption(
        "Şifrenizi girdikten sonra sol menüden **Şifre Değiştir** ile kendi şifrenizi "
        "belirleyebilirsiniz. Şifrenizi unuttuysanız sistem yöneticisine başvurun."
    )
