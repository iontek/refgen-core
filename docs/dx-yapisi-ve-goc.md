# dx Yapısı ve Göç Spesifikasyonu

> **Proje:** dxm (RefGen mikroservis platformu) · **Tarih:** 2026-06-17 · **Sürüm:** Taslak v0.1
> **İlgili:** [mimari-vizyon.md](./mimari-vizyon.md)
> **Dil notu:** Türkçe; PDF'e dönüştürülmek üzere.

---

## 1. Amaç

Bu doküman iki şeyi yapar:
1. Mevcut **dx** CLI'sinin **net yapı haritası** (modül modül incelenerek çıkarıldı).
2. Yeni mikroservis mimarisine (**dxm**) **göç spesifikasyonu** — *"`api.py` = kontrat spec'i"* ilkesiyle her yeni servisin ne sunması gerektiğini tanımlar; **taşınmayacak ölü kodu** işaretler.

İlke (bkz. mimari-vizyon §"Temel Prensipler"): **kontrat korunur → dx ve mevcut istemciler hiç değişmeden çalışır** (strangler-fig). **Göç = temizlik**, kopyalama değil.

---

## 2. dx kuşbakışı

- **Dil/çerçeve:** Python + **Click** (CLI), Rich + questionary + prompt_toolkit (TUI).
- **Konum:** `refgen-platform/cli/dx/`
- **Giriş:** `pyproject.toml → dx = dx.cli:main`
- **İki yüz:**
  1. **Scriptable CLI** — `dx panel list`, `dx run design …`
  2. **İnteraktif TUI** — çıplak `dx`, `dx panel`, `dx run`, `dx mcp`, `dx recipe` (accordion konsolu)
- **Backend bağımlılığı:** Django REST (`api.py` üzerinden, tek kanal) **+** tek WebSocket (`dx shell`).

---

## 3. Modül haritası

| Dosya | Satır | Rol | Göçte hedefi |
|---|---|---|---|
| **cli.py** | 5720 | komutlar **+** TUI accordion motoru | komutlar → kontrat; TUI → istemci (as-is) |
| **api.py** | 494 | Django REST HTTP client (**kontrat**) | servislerin spec'i; gateway'e re-point |
| **shell.py** | 149 | PTY/WebSocket shell köprüsü | gateway WS proxy gerektirir (en zor parça) |
| **intervalops.py** | 124 | interval cebiri (region) | domain lib / motor (bedtools) |
| **output.py** | 123 | çıktı biçimleme (table/tsv/csv/json) | istemci (dx) ile kalır |
| **config.py** | 51 | token/server saklama | **multi-profile** eklenecek |
| **setops.py** | 34 | küme cebiri (gen) | domain lib / panels-svc |
| **version.py** | 31 | komut envanteri/versiyon | trivial |
| **reference.py** | 24 | referans yardımcı | trivial |

---

## 4. Komut ağacı (tam)

**Üst seviye:** `login` · `logout` · `whoami` · `access` · `version` · `shell`(+`sh`) · `copilot` · `analyst` · `chat` · `audit` · `up` · *(gizli:* `clinvar`/`hotspots`/`gene` → `genes` altında*)*

**Gruplar:**
- **panel** → list · set-type · compare · which · new · add-gene · import · doc · remove-gene · add-region · regions · remove-region · validate · export · approve · lock · reject · deprecate · archive · delete · pick · show · genes · oligos · pending · history · members · add-member · remove-member
- **run** → pick · list · show · provenance · verify · graph · watch · design · assemble · oligos · genscript · view · report · artifact · seqs · order · new
- **mcp** → status · list · pick · start · stop · restart
- **user** → list · create · passwd · delete · disable · enable
- **lit** → pubmed · save · index · ask · zotero · store · erase · sync · url · list
- **agent** → list · show · graph · run
- **adapter** → list · create
- **recipe** → list · show · create · graph · pick
- **gene/genes** → list (+ clinvar/hotspots/info)
- **define** → region

---

## 5. TUI accordion mimarisi

Çekirdek = **`_tree_frame`**: spec-driven, recursive, full-screen accordion (kendi prompt_toolkit App'i).

- **Spec ile sürülür:** `levels` (her seviye: specs/fetch/actions/decorate/leaf), `page`, `multi_select`, `ops` (küme cebiri), `title`, `hint`.
- **Lazy ağaç:** `children()` veriyi gerektiğinde çeker; düğümler içe açılır (▼/▶).
- **Bağlam-duyarlı aksiyon bölgesi:** 2+ seçim → küme cebiri + delete; yoksa düğüme özel aksiyonlar.
- **"Intent" döndürür** (`act, value, node`); gezinme app içinde, yalnız seçilen aksiyon çıkar.
- **Jupyter-tarzı session log:** In[n]/Out[n], katlanabilir, **renkli/yanıp sönen state button** (e/h onayı).
- **Domain accordion'ları:** `_panel_accordion` · `_run_accordion` · `_mcp_accordion` · `_recipe_accordion`; `_shell` = üst döngü.

**Göç:** %100 client-side, yalnız `api.py`'den konuşur → **as-is taşınır**, sadece gateway'e re-point. Web GUI bunu KULLANMAZ (terminal UI); web ayrı istemci, aynı API.

---

## 6. Kontrat → Servis Eşlemesi  *(GÖÇ SPEC'İ — bu dokümanın kalbi)*

`api.py`'deki her çağrı = yeni servisin sunması gereken endpoint. Gruplandırılmış hâli:

### identity-svc
| dx çağrısı | endpoint |
|---|---|
| `login` | `POST /api/auth/token/` |
| (refresh) | `POST /api/auth/refresh/` |
| `whoami` | `GET /api/users/me/` |
| `list/create_user` | `GET/POST /api/users/` |
| `set_user_password` | `POST /api/users/{id}/set-password/` |
| `delete_user` | `DELETE /api/users/{id}/` |
| `set_user_active` | `POST /api/users/{id}/enable\|disable/` |
| `access` | `GET /api/access/` |

### panels-svc
| dx çağrısı | endpoint |
|---|---|
| list/get/create panel | `GET /api/panels/` (?include_archived) · `GET/POST /api/panels/{id}/` |
| set_panel_type/update | `PATCH /api/panels/{id}/` |
| **state machine** | `POST /api/panels/{id}/` + `validate/` · `reject/` · `lock/` · `deprecate/` · **`unlock/`** · `archive/` |
| pending / history | `GET /api/panels/pending/` · `GET /api/panels/{id}/history/` |
| compare / with-gene | `GET /api/panels/compare/` · `GET /api/panels/with-gene/` |
| validate genes | `GET /api/panels/{id}/validate-genes/` |
| genes | `POST /api/panels/{id}/add-genes/` · `DELETE /api/panel-genes/{id}/` |
| regions | `GET/POST /api/panels/{id}/regions/` · `DELETE …/regions/{rid}/` |
| members | `GET/POST /api/panels/{id}/members/` · `DELETE …/members/{mid}/` |
| versions | `GET /api/versions/` (content_hash) |
| export | `POST /api/panels/{id}/export/` (?vendor) |
| gene catalog | `GET /api/gene-catalog/{symbol}/` · `/stats/` · `/exons/` |

### design-svc  *(probe-design — motora dokunanlar burada)*
| dx çağrısı | endpoint |
|---|---|
| runs | `GET/POST /api/probe-design/runs/` · `GET …/{id}/` |
| design/assemble | `POST …/{id}/design/` · `…/{id}/assemble/` |
| oligos/provenance/graph/igv/artifact | `GET …/{id}/…` |
| adapter-sets | `GET/POST /api/probe-design/adapter-sets/` |
| recipes | `GET/POST /api/probe-design/runs/recipes/` |
| panel oligos | `GET /api/probe-design/panels/{id}/oligos/` |
| **→ motor (MCP) passthrough** | `clinvar/{gene}` · `hotspots/{gene}` · `lit/` · `agents/` · `agents/run/` · `analyst/` |

### registry / gateway
`GET /api/mcp-status/` · `GET /api/registry/mcp-servers/[{id}]` · `POST /api/registry/lifecycle/{name}/{action}/` · `…/lifecycle/all/{action}/`

### audit
`GET /api/audit-events/` (?limit, entity_type, user)

### Mekanik (gateway + servisler korumalı)
- **Önek:** tüm yollar `/api/...`
- **Auth:** JWT **access + refresh**; 401 → refresh → **bir kez** retry; token `Bearer` header.
- **Pagination:** DRF `{ "results": [...] }` (dx her listede `d.get("results", d)` yapar).
- **Hata:** `ApiError(status, body)` — tutarlı şekil.
- **Timeout:** default 60s; `lifecycle/all` 600s; `run design` 900s; `lit` 1800s; `hotspots`/`analyst` 120–180s.

> **Kural:** Gateway bu 3 şeyi korursa — `/api` öneki + DRF pagination + auth şekilleri — **dx ve `:5174` frontend hiç değişmeden çalışır.**

---

## 7. Kimlik & ayar (config.py) — tek-profil boşluğu

- Saklama: `~/.dx/config.json` (`DX_HOME` ile değişir), izin **0600**.
- Alanlar: `server`, `username`, `access`, `refresh`. Server `DX_SERVER` env'i veya config'ten.
- **Boşluk:** Bugün **tek profil** (tek server + tek hesap). Çok-merkez/ağaç-tenant için **multi-profile** gerekir: `dx use <profil>` / `~/.dx/profiles/`, her profil = {server + token}. → `config.py`'de küçük, izole bir ekleme.
- **Kolaylık:** gateway'e geçiş trivial — `DX_SERVER=<gateway>` veya `dx login --server <gateway>`.

---

## 8. shell.py — WebSocket backend bağımlılığı (REST-dışı tek parça)

- `dx shell` = yerel TTY ↔ sunucunun **audited WebSocket shell'i** (`/ws/shell/?token=…`).
- Protokol: client `{input,resize}` ↔ server `{output,exit,error}`.
- **Göç:** Gateway WebSocket'i **proxy'lemeli** ve **upgrade'de token doğrulamalı** (token query param ile gelir). Audited shell + workspace'e bağlı → muhtemelen **EDGE'de** çalışır. **En zor / en son taşınacak parça.**
- **Açık soru:** `dx shell` müşteri ürününde mi, yoksa iç/ops aracı mı? Önceliklendirme.

---

## 9. Domain cebiri + çıktı

- **`output.py`** = sunum → **dx ile kalır** (web GUI kendi render'ını yapar).
- **`setops.py`** = ayrık eleman (gen) küme cebiri; **`intervalops.py`** = interval (region) cebiri (pad/merge/subtract/intersect/complement, **1:1 bedtools**). İkisi de temiz, gold-standard.
- **Göç:** yetkili işlemler server-side (panel küme işlemleri `panels-svc`; interval ölçekte **motor/bedtools**). Client kopyası önizleme için. Cebir paylaşılan domain lib'e taşınabilir.

---

## 10. Ölü kod / taşınmayacaklar

> **Önemli:** Aşağıdakiler **güçlü aday**, kesin değil. Taşımadan önce her biri **birebir doğrulanır**. Platform repo'sunda **silinmez** (governance gate'i kullanıcının); sadece **göçe taşınmaz.**

- **`api.py`: temiz** ✅ — tüm fonksiyonlar kullanılıyor.
- **`cli.py`: kullanılmıyor görünen özel yardımcılar** (refactor artığı — accordion sistemine yenilmiş eski sürümler):

| Aday | Muhtemelen yerine geçen |
|---|---|
| `_check` | `_tree_frame` |
| `_panel_zone_actions` | spec `actions` |
| `_show_panel_genes` | `_panel_accordion` |
| `_set_ops` | `_run_set_op` |
| `_panel_detail` (~130 satır) | `_panel_accordion` |
| `_command_accordion` | `_shell` |

- **Yarım kalmış işaret ≈ yok** (TODO/FIXME yok; birkaç meşru `pass`/`except`).

---

## 11. Göç notları / kontrol listesi

1. **Gateway 3 şeyi korur** → dx hiç değişmez: `/api` öneki · DRF `{results}` pagination · JWT access/refresh şekilleri.
2. **dx tarafı değişiklikleri minimal:** `DX_SERVER`→gateway; **multi-profile** ekle (küçük); gerisi aynı.
3. **TUI as-is taşınır** (client-side); yalnız re-point.
4. **shell** en son/zor (WS proxy + edge backend).
5. **Web GUI ayrı** istemci — API'yi paylaşır, TUI'yi değil.
6. **Ölü kodu taşıma**, §10 listesini doğrulayıp dışarıda bırak.
7. **Servisler `api.py` kontratını** birebir karşılar (§6).

---

## 12. Açık sorular

1. `panels/{id}/unlock/` mevcut, ama "locked asla unlock edilmez" kuralıyla çelişiyor → governance-gated mı? panels-svc'de netleştir.
2. `dx shell` ürün özelliği mi, iç/ops aracı mı?
3. Multi-profile UX (`dx use <profil>`).
4. TUI motorunu `cli.py`'den ayrı modüle bölmek (temizlik — göç için şart değil).

---

*Bu doküman, dx'in modül-modül incelenmesinden (2026-06-17) çıkarılmıştır. Servisler kuruldukça güncellenir.*
