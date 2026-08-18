"""Supabase bağlantısı ve sorgu yardımcıları.

Bağlantı her zaman giriş yapan kullanıcının kimliğiyle kurulur; böylece
veritabanındaki 97 RLS politikası ve rol bazlı maliyet maskeleme aynen çalışır.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from supabase import Client, create_client


# ---------------------------------------------------------------- bağlantı
def _ayar(anahtar: str, varsayilan: str | None = None) -> str | None:
    """secrets.toml veya ortam değişkeninden ayar okur."""
    try:
        if anahtar in st.secrets:
            return st.secrets[anahtar]
    except Exception:
        pass
    import os

    return os.environ.get(anahtar, varsayilan)


def istemci() -> Client:
    """Oturuma bağlı Supabase istemcisini döndürür (yoksa oluşturur)."""
    if "sb" not in st.session_state:
        url = _ayar("SUPABASE_URL")
        key = _ayar("SUPABASE_KEY")
        if not url or not key:
            st.error(
                "Supabase bağlantı bilgileri bulunamadı. "
                "`.streamlit/secrets.toml` dosyasına SUPABASE_URL ve SUPABASE_KEY ekleyin."
            )
            st.stop()
        st.session_state.sb = create_client(url, key)
    return st.session_state.sb


def kullanici_id() -> str:
    """Önbellek anahtarı olarak kullanılır — roller arası veri sızmasını önler."""
    return st.session_state.get("kullanici_id", "anonim")


# ---------------------------------------------------------------- filtre
# PostgREST'te `in` ve `is` Python anahtar kelimesi olduğu için metot adları `in_` / `is_`.
_OP_AD = {"in": "in_", "is": "is_", "not": "not_"}


def _filtre_uygula(q, alan: str, op: str, deger):
    metot = getattr(q, _OP_AD.get(op, op))
    if op == "in" and isinstance(deger, str):
        deger = [x.strip() for x in deger.strip("()").split(",") if x.strip()]
    return metot(alan, deger)


# ---------------------------------------------------------------- sorgu
@st.cache_data(ttl=20, show_spinner=False)
def _sorgu(
    _sb: Client,
    _kullanici: str,
    tablo: str,
    select: str,
    filtreler_json: str,
    sira: str | None,
    tersine: bool,
    limit: int | None,
) -> pd.DataFrame:
    q = _sb.table(tablo).select(select)
    for alan, op, deger in json.loads(filtreler_json):
        q = _filtre_uygula(q, alan, op, deger)
    if sira:
        q = q.order(sira, desc=tersine)
    if limit:
        q = q.limit(limit)
    veri = q.execute().data or []
    return pd.DataFrame(veri)


def sorgu(
    tablo: str,
    select: str = "*",
    filtreler: list[tuple] | None = None,
    sira: str | None = None,
    tersine: bool = False,
    limit: int | None = None,
) -> pd.DataFrame:
    """Tablodan/görünümden veri çeker ve DataFrame döndürür.

    filtreler: [("durum", "eq", "aktif"), ("fiziksel", "gt", 0)]
    """
    return _sorgu(
        istemci(),
        kullanici_id(),
        tablo,
        select,
        json.dumps(filtreler or []),
        sira,
        tersine,
        limit,
    )


def tek(tablo: str, select: str = "*", filtreler: list[tuple] | None = None) -> dict | None:
    df = sorgu(tablo, select, filtreler, limit=1)
    return None if df.empty else df.iloc[0].to_dict()


def sayi(tablo: str, filtreler: list[tuple] | None = None) -> int:
    """Kayıt sayısını döndürür (veri çekmeden)."""
    q = istemci().table(tablo).select("*", count="exact", head=True)
    for alan, op, deger in filtreler or []:
        q = _filtre_uygula(q, alan, op, deger)
    return q.execute().count or 0


# ---------------------------------------------------------------- yazma
def ekle(tablo: str, kayit: dict | list[dict]) -> list[dict]:
    sonuc = istemci().table(tablo).insert(kayit).execute()
    onbellek_temizle()
    return sonuc.data or []


def guncelle(tablo: str, kayit: dict, filtreler: list[tuple]) -> list[dict]:
    q = istemci().table(tablo).update(kayit)
    for alan, op, deger in filtreler:
        q = _filtre_uygula(q, alan, op, deger)
    sonuc = q.execute()
    onbellek_temizle()
    return sonuc.data or []


def sil(tablo: str, filtreler: list[tuple]) -> None:
    q = istemci().table(tablo).delete()
    for alan, op, deger in filtreler:
        q = _filtre_uygula(q, alan, op, deger)
    q.execute()
    onbellek_temizle()


def rpc(fonksiyon: str, parametreler: dict | None = None):
    """Veritabanı iş mantığı fonksiyonunu çağırır (FEFO, landed cost, sevkiyat…)."""
    sonuc = istemci().rpc(fonksiyon, parametreler or {}).execute()
    onbellek_temizle()
    return sonuc.data


def onbellek_temizle() -> None:
    _sorgu.clear()
    referans.clear()


# ---------------------------------------------------------------- referans veriler
@st.cache_data(ttl=180, show_spinner=False)
def referans(_sb: Client, _kullanici: str) -> dict:
    """Sık kullanılan sabit listeler (depo, lokasyon, kanal, marka, kategori, cari…)."""

    def al(tablo, select="*", filtre=None, sira=None):
        q = _sb.table(tablo).select(select)
        if filtre:
            q = q.eq(*filtre)
        if sira:
            q = q.order(sira)
        return q.execute().data or []

    cariler = al("cariler", filtre=("aktif", True), sira="unvan")
    ayarlar = {a["anahtar"]: a["deger"] for a in al("ayarlar")}
    return {
        "depo": al("depolar", filtre=("aktif", True), sira="ad"),
        "lokasyon": al("lokasyonlar", filtre=("aktif", True), sira="kod"),
        "kanal": al("kanallar", filtre=("aktif", True), sira="ad"),
        "marka": al("markalar", filtre=("aktif", True), sira="ad"),
        "kategori": al("kategoriler", filtre=("aktif", True), sira="ad"),
        "cari": cariler,
        "tedarikci": [c for c in cariler if c["tip"] == "tedarikci"],
        "musteri": [c for c in cariler if c["tip"] == "musteri"],
        "masraf": al("masraf_kalem_tipleri", filtre=("aktif", True), sira="sira"),
        "ayar": ayarlar,
    }


def ref() -> dict:
    return referans(istemci(), kullanici_id())


def ref_secim(tip: str, alan: str = "ad") -> dict:
    """{id: görünen ad} sözlüğü — selectbox için."""
    return {x["id"]: x.get(alan) or x.get("ad") or x.get("unvan") for x in ref().get(tip, [])}


def ayar(anahtar: str, varsayilan=None):
    d = ref()["ayar"].get(anahtar, varsayilan)
    if isinstance(d, str):
        return d.strip('"')
    return d
