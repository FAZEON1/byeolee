# KAYRAN ERP — Streamlit

Kozmetik ürünler için stok, parti/SKT ve ithalat maliyet (landed cost) yönetimi.
Arayüz **Streamlit**, veritabanı **Supabase (PostgreSQL + RLS)**.

19 ekran · 15 rapor · 8 rol · rol bazlı maliyet maskeleme veritabanı seviyesinde.

---

## 1. Streamlit Community Cloud'a kurulum

Terminal bilmenize gerek yok — her şey tarayıcıdan yapılır. Toplam 10-15 dakika.

### Adım 1 — GitHub hesabı

Hesabınız yoksa: https://github.com/join (ücretsiz, e-posta doğrulaması ister).

### Adım 2 — Boş depo oluşturun

https://github.com/new adresine gidin:

- **Repository name:** `kayran-erp`
- **Public / Private:** ikisi de olur. Private seçerseniz Adım 5'te ek bir yetki vermeniz gerekir.
- Alttaki "Add a README file" kutusunu **işaretlemeyin**.
- **Create repository**'ye basın.

### Adım 3 — Dosyaları yükleyin

Zip'i bilgisayarınızda bir klasöre çıkarın. Yeni deponuzda:

**Add file → Upload files** → çıkardığınız klasörün **içindeki** dosyaları
(klasörün kendisini değil) sürükleyip bırakın → **Commit changes**.

> `lib` ve `modules` klasörlerini de sürüklemeyi unutmayın; alt dosyalarıyla birlikte yüklenirler.
>
> `.streamlit` klasörü nokta ile başladığı için bazı işletim sistemlerinde görünmez.
> Yüklenemezse sorun değil — o klasör yalnızca tema içindir, uygulama onsuz da çalışır.
> İsterseniz sonra **Add file → Create new file** deyip dosya adına
> `.streamlit/config.toml` yazarak elle ekleyebilirsiniz.

Yükleme bitince depoda `streamlit_app.py`, `requirements.txt`, `lib/`, `modules/`
görünüyor olmalı.

### Adım 4 — Streamlit Cloud'a girin

https://share.streamlit.io adresine gidin, **Continue with GitHub** ile giriş yapın ve
**Authorize streamlit**'e basın.

Private depo seçtiyseniz ek olarak: sol üstteki GitHub kullanıcı adınız →
**Settings → Linked accounts → Source control → Connect here** → tekrar
**Authorize streamlit**.

### Adım 5 — Uygulamayı yayınlayın

1. Sağ üstte **Create app**.
2. "Do you already have an app?" sorusuna **Yup, I have an app**.
3. Alanları doldurun:
   - **Repository:** `<kullanici-adiniz>/kayran-erp`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** istediğiniz alt alan adı (örn. `kayran-erp`) — boş bırakırsanız otomatik atanır
4. **Advanced settings**'e tıklayın. Python sürümü varsayılan (3.12) kalabilir.
   **Secrets** kutusuna şunu yapıştırın:

   ```toml
   SUPABASE_URL = "https://sneculeiqfvsmlkoojiv.supabase.co"
   SUPABASE_KEY = "sb_publishable_q43T-btRs_Kyah4_wbD0zw_u_D_J94m"
   ```

   **Save**'e basın.
5. **Deploy**'a basın. İlk kurulum 2-5 dakika sürer (bağımlılıklar indiriliyor).

Hazır olduğunda adresiniz: `https://<sectiginiz-ad>.streamlit.app`

> Bu anahtar "publishable" (yayınlanabilir) anahtardır — tek başına hiçbir veriye erişim
> vermez. Tüm yetkilendirme kullanıcı girişine ve veritabanındaki 97 RLS politikasına
> bağlıdır. Yine de gereksiz yere paylaşmayın.

### Adım 6 — Erişimi sınırlayın (önerilir)

Uygulama adresi herkese açıktır (giriş ekranıyla korunur). Sadece ekibiniz görebilsin
isterseniz: uygulama sayfasında sağ alttaki **Manage app → Settings → Sharing** →
"Only specific people can view this app" → ekibinizin e-postalarını ekleyin.

### Sonradan güncelleme

GitHub'daki dosyayı değiştirip commit ettiğinizde uygulama kendini otomatik yeniler.
Elle yenilemek için: uygulama sayfasında **Manage app → Reboot**.

### Resmî belgeler

- Yayınlama: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Secrets yönetimi: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- GitHub bağlama: https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account

---

## 2. Yerelde çalıştırma

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # değerleri düzenleyin
streamlit run streamlit_app.py
```

Tarayıcıda http://localhost:8501 açılır.

---

## 3. Giriş bilgileri

Kullanıcılar **e-posta değil kullanıcı adı** ile girer.

| Kullanıcı adı | Ad | Rol | Başlangıç şifresi |
|---|---|---|---|
| `ibrahim` | İbrahim | Sistem Yöneticisi | `1234` |
| `hakan` | Hakan | Yönetici | `1234` |
| `mustafa` | Mustafa | Yönetici | `1234` |
| `ebubekir` | Ebubekir | Yönetici | `1234` |

Herkes giriş yaptıktan sonra sol menüdeki **🔑 Şifre Değiştir** ile kendi şifresini
belirleyebilir. Yeni şifre en az **6 karakter** olmalıdır (Supabase kuralı).

### Nasıl çalışıyor

Kullanıcı `hakan` yazar; uygulama bunu arka planda `hakan@kayranerp.com` adresine
çevirip Supabase Auth'a sorar. Alan adı `secrets.toml` içindeki `KULLANICI_ALAN_ADI`
ile değiştirilebilir. Kullanıcı e-posta görmez, ancak oturum gerçek bir Supabase
oturumu olduğu için RLS, maliyet maskeleme ve denetim izi olduğu gibi çalışır.

> **Neden şifreler secrets.toml'da tutulmuyor?** İki nedenle: (1) çalışan uygulamada
> secrets dosyası değiştirilemez, yani kullanıcı kendi şifresini yenileyemezdi;
> (2) veritabanı kimin bağlandığını bilemez, dolayısıyla rol bazlı maliyet maskeleme
> ve "kim değiştirdi" kaydı çalışmazdı.

### Yeni kullanıcı ekleme

Supabase SQL Editor'de (sistem yöneticisi hesabıyla ERP'ye girmiş olmanız gerekmez,
SQL Editor doğrudan çalışır):

```sql
select erp_kullanici_olustur(
  'ayse@kayranerp.com',   -- kullanıcı adı + @kayranerp.com
  'Gecici123',            -- başlangıç şifresi (en az 6 karakter)
  'Ayşe Yılmaz',          -- ad soyad
  'depo_sorumlusu'        -- rol
);
```

Kullanıcı bundan sonra `ayse` yazarak girer.

### Şifre sıfırlama (unutan kullanıcı için)

```sql
update auth.users
   set encrypted_password = extensions.crypt('Yeni1234', extensions.gen_salt('bf'))
 where email = 'ayse@kayranerp.com';
```

---

## 4. Dosya yapısı

```
streamlit_app.py        Giriş noktası: oturum kontrolü, rol bazlı menü, yönlendirme
requirements.txt        Python bağımlılıkları
.streamlit/
  config.toml           Tema ve sunucu ayarları
  secrets.toml.example  Bağlantı anahtarı şablonu (kopyalayıp doldurun)
lib/
  db.py                 Supabase bağlantısı, sorgu/yazma yardımcıları, önbellek
  auth.py               Giriş, rol, yetki matrisi, giriş ekranı
  ui.py                 Biçimlendirme, KPI kartları, tablolar, grafikler
modules/                Her ekran ayrı bir modül (19 dosya)
  dashboard.py  partiler.py  urunler.py  stok.py  hareketler.py
  malkabul.py   sayim.py     satinalma.py ithalat.py cariler.py
  siparisler.py sevkiyat.py  iadeler.py   raporlar.py bildirimler.py
  ayarlar.py    kullanicilar.py denetim.py
```

**Yeni ekran eklemek:** `modules/` altına `goster()` fonksiyonu olan bir dosya açın,
`streamlit_app.py` içindeki `gruplar` sözlüğüne bir `_s(modul.goster, "Ad", "🔧", "url")`
satırı ekleyin. Rol kısıtı için `if auth.yetkili("depo"):` bloğu içine koyun.

---

## 5. Güvenlik modeli

Bağlantı her zaman **giriş yapan kullanıcının kimliğiyle** kurulur. Bu sayede:

- Veritabanındaki **97 RLS politikası** aynen çalışır.
- Maliyet, kâr marjı ve cari bakiye alanları yetkisiz rollerde **veritabanı tarafından
  NULL döner** — arayüzde gizlenmekle kalmaz (BR-14).
- Önbellek anahtarına kullanıcı kimliği dahil edilir; roller arası veri sızması olmaz
  (`lib/db.py` içindeki `kullanici_id()`).

Doğrulama: Satış rolüyle giriş yapın — Parti/SKT ekranında 54 satırın hepsi görünür,
maliyet sütunları hiç yoktur.

---

## 6. Bilinen davranışlar

**Tarayıcı yenilemesi (F5) oturumu düşürür.** Streamlit oturum durumunu sunucu belleğinde
tutar; sayfa tamamen yenilenince yeni oturum başlar. Uygulama içi menü gezinmesi bu sorunu
yaşamaz — sadece manuel yenilemede tekrar giriş gerekir. Kalıcı oturum isterseniz
çerez tabanlı saklama (`extra-streamlit-components`) eklenebilir.

**Veri önbelleği 20 saniyedir.** Başka bir kullanıcı kayıt eklediğinde en geç 20 saniye
içinde görürsünüz; hemen görmek için kenar çubuğundaki **⟳ Yenile** düğmesini kullanın.

**Community Cloud uykuya geçer.** Ücretsiz planda uygulama bir süre kullanılmazsa uyur;
ilk açılışta 30–60 saniye bekleme olur. Sürekli açık kalması için Streamlit'in ücretli
planı veya kendi sunucunuz gerekir.

---

## 7. Canlıya geçiş kontrol listesi

- [ ] Üç demo hesabın şifresi değiştirildi
- [ ] Gerçek kullanıcılar eklendi (Supabase → Authentication → Add user), roller atandı
- [ ] **Ayarlar** ekranından SKT uyarı eşikleri işletmenize göre ayarlandı (180 / 90 / 30 gün)
- [ ] Her satış kanalının komisyon oranı ve minimum raf ömrü güncellendi
- [ ] Örnek veri temizlendi, gerçek katalog yüklendi
- [ ] Fiziksel sayım yapılıp açılış stoğu **parti ve SKT bilgisiyle** girildi
- [ ] Döviz kurları güncellendi (şu an örnek: EUR 48,50 / USD 41,80)
- [ ] Supabase Pro + PITR yedekleme açıldı
- [ ] Günlük SKT kontrolü `pg_cron` ile otomatikleştirildi:

```sql
create extension if not exists pg_cron;
select cron.schedule('gunluk-skt', '0 6 * * *', $$select gunluk_skt_kontrol()$$);
```

---

## 8. Veritabanı

- **Proje:** KAYRAN-ERP (`sneculeiqfvsmlkoojiv`) · Frankfurt (eu-central-1)
- **Panel:** https://supabase.com/dashboard/project/sneculeiqfvsmlkoojiv
- **Yapı:** 49 tablo · 12 görünüm · 97 RLS politikası · 14 iş mantığı fonksiyonu

Ana iş mantığı arayüzde değil veritabanında çalışır — arayüz sadece bu fonksiyonları çağırır:

| Fonksiyon | Ne yapar |
|---|---|
| `fefo_tahsis` | SKT'si en yakın uygun partiyi seçer (kanal eşiği ve SKT kontrolüyle) |
| `siparis_rezerve_et` | Siparişi FEFO'ya göre partilere bağlar, stok rezerve eder |
| `siparis_sevk_et` | Rezerveyi çözer, stok hareketi yazar, SKT'yi son kez doğrular |
| `landed_cost_dagit` | Masrafları dağıtım anahtarlarına göre yayıp birim maliyeti yazar |
| `mal_kabul_tamamla` | Parti oluşturur, SKT hesaplar, stoğa alır |
| `sayim_onayla` | Sayım farkını yetkili onayıyla stoğa işler |
| `parti_imha_et` / `geri_cagirma_baslat` | İmha ve geri çağırma zinciri |
| `gunluk_skt_kontrol` | SKT'si geçen partileri işaretler, uyarı üretir |
