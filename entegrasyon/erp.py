"""ERP (Supabase) tarafı — entegrasyon işçisinin veritabanı arayüzü.

Servis anahtarı (service_role) KULLANILMAZ. İşçi, `entegrasyon@...` adlı
normal bir ERP kullanıcısı olarak giriş yapar; böylece RLS politikaları,
maliyet maskeleme ve denetim izi aynen çalışmaya devam eder.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from supabase import create_client


def _cevre(ad: str, varsayilan: str | None = None, zorunlu: bool = False) -> str:
    d = os.environ.get(ad, varsayilan)
    if zorunlu and not d:
        raise SystemExit(f"HATA: {ad} ortam değişkeni tanımlı değil.")
    return d or ""


class Erp:
    def __init__(self):
        url = _cevre("SUPABASE_URL", zorunlu=True)
        key = _cevre("SUPABASE_KEY", zorunlu=True)
        kullanici = _cevre("ERP_KULLANICI", zorunlu=True)
        sifre = _cevre("ERP_SIFRE", zorunlu=True)
        alan = _cevre("KULLANICI_ALAN_ADI", "kayranerp.com")
        if "@" not in kullanici:
            kullanici = f"{kullanici}@{alan}"

        self.sb = create_client(url, key)
        sonuc = self.sb.auth.sign_in_with_password(
            {"email": kullanici, "password": sifre})
        if not sonuc.user:
            raise SystemExit("HATA: ERP girişi başarısız (kullanıcı adı/şifre).")
        self.kullanici_id = sonuc.user.id

    def kapat(self) -> None:
        try:
            self.sb.auth.sign_out()
        except Exception:
            pass

    # ------------------------------------------------------------ kanal
    def kanal(self, kod: str) -> dict:
        y = self.sb.table("kanallar").select("*").eq("kod", kod).maybe_single().execute()
        if not y or not y.data:
            raise SystemExit(f"HATA: '{kod}' kodlu satış kanalı bulunamadı.")
        return y.data

    # ------------------------------------------------------------ sipariş
    def siparis_kaydet(self, kanal_id: int, siparis: dict) -> dict:
        y = self.sb.rpc("pazaryeri_siparis_kaydet",
                        {"p_kanal_id": kanal_id, "p_siparis": siparis}).execute()
        return y.data or {}

    def paket_id_ile_siparis(self, kanal_id: int, kanal_siparis_no: str) -> dict | None:
        y = (self.sb.table("satis_siparisleri")
             .select("id,kanal_paket_id,kanal_siparis_no")
             .eq("kanal_id", kanal_id).eq("kanal_siparis_no", kanal_siparis_no)
             .maybe_single().execute())
        return (y.data if y else None) or None

    # ------------------------------------------------------------ stok
    def gonderilecek_stok(self, kanal_id: int) -> list[dict]:
        y = self.sb.rpc("kanal_gonderilecek_stok", {"p_kanal_id": kanal_id}).execute()
        return y.data or []

    # ------------------------------------------------------------ bildirim
    def bildirim_bekleyenler(self, kanal_id: int) -> list[dict]:
        y = (self.sb.table("v_kanal_bildirim_bekleyen").select("*")
             .eq("kanal_id", kanal_id).execute())
        return y.data or []

    def bildirim_isle(self, siparis_id: int, durum: str, hata: str | None = None) -> None:
        (self.sb.table("satis_siparisleri").update({
            "kanal_bildirim_durumu": durum,
            "kanal_bildirim_tarihi": datetime.now(timezone.utc).isoformat(),
            "kanal_bildirim_hata": (hata or "")[:500] or None,
        }).eq("id", siparis_id).execute())

    # ------------------------------------------------------------ log
    def log_yaz(self, kanal_id: int, islem: str, baslangic: datetime,
                basarili: bool, okunan=0, yazilan=0, atlanan=0, hatali=0,
                detay=None, hata_mesaji: str | None = None) -> None:
        try:
            self.sb.table("entegrasyon_log").insert({
                "kanal_id": kanal_id,
                "islem": islem,
                "baslangic": baslangic.isoformat(),
                "bitis": datetime.now(timezone.utc).isoformat(),
                "basarili": basarili,
                "okunan": okunan, "yazilan": yazilan,
                "atlanan": atlanan, "hatali": hatali,
                "detay": detay or {},
                "hata_mesaji": (hata_mesaji or "")[:2000] or None,
            }).execute()
        except Exception as e:      # log yazamamak işi durdurmasın
            print(f"  ! log yazılamadı: {e}")

    def son_basarili_bitis(self, kanal_id: int, islem: str) -> datetime | None:
        y = (self.sb.table("entegrasyon_log").select("bitis")
             .eq("kanal_id", kanal_id).eq("islem", islem).eq("basarili", True)
             .order("bitis", desc=True).limit(1).execute())
        veri = y.data or []
        if not veri or not veri[0].get("bitis"):
            return None
        return datetime.fromisoformat(veri[0]["bitis"].replace("Z", "+00:00"))
