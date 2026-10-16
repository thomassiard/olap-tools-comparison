# Mjerenje performansi OLAP alata (Instacart / ClickHouse)

Skripte i protokol za diplomski rad *Analiza i usporedba OLAP alata*. Mjeri se **isti skup od 9 upita
(Q1–Q9) i 4 koraka skalabilnosti (S1–S4)** u svih pet alata, uz **ponovljena pokretanja**, a za svaki
upit se bilježe **dvije metrike**:

| Metrika | Značenje |
|---|---|
| `data_ms` – vrijeme pristupa podacima | od slanja upita do primitka rezultata |
| `render_ms` – vrijeme generiranja vizualizacije | od primitka podataka do iscrtanog grafikona |

Ukupno vrijeme do prikaza = `data_ms` + `render_ms`. ClickHouse (HTTP) služi kao **osnovna linija** (nema
vizualizacije, samo `data_ms`; `server_ms` je vrijeme koje izvješćuje sam poslužitelj).

## 1. Skup upita

Definirani su u `queries.json` (SQL za ClickHouse, shema `instacart`). Veličina podataka: **mali** (≤ 50 tis. redaka,
tablica `products`), **srednji** (1,4–3,4 M, `orders`, `order_products_train`), **veliki** (32,4 M, `order_products_prior`).
Složenost: filtriranje, grupiranje, spajanje 2/3/4 tablice. Upiti Q8 i Q9 imaju kontrolnu sumu (rezultat mora zbrojiti
32.434.489) – skripta upozori ako ne odgovara. Skalabilnost: isti upit nad podskupovima S1–S4 (≈1, 5, 10 i 32,4 M redaka).

## 2. Priprema (Windows PowerShell)

```powershell
cd olap-benchmark
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium          # samo za mjerenje crtanja u Supersetu/Metabaseu
copy config.example.json config.json # upiši lozinke i ID baza; config.json je u .gitignore
python bench.py sysinfo              # zapisuje OS/CPU/RAM u results\sysinfo.json
python bench.py rows                 # stvarni broj redaka u S1..S4 -> results\scale_rows.json
```
ID baze: Superset *Settings → Database Connections* (broj u URL-u/API-ju), Metabase *Admin → Databases* (broj u URL-u).

**Uvjeti mjerenja (zapiši ih u rad):** isto računalo za sve alate; zatvorene ostale aplikacije; ista Docker alokacija
resursa; računalo na struji; mjerenja jedno za drugim, ne paralelno. 1 zagrijavanje (odbačeno) + **10 ponavljanja** za
automatska mjerenja, **5 ponavljanja** za ručna (Power BI, Tableau). Izvješćuju se medijan, min–maks i kvartili.

## 3. Automatska mjerenja (ClickHouse, Superset, Metabase)

```powershell
python bench.py clickhouse
python bench.py superset
python bench.py metabase
```
Svaka podkomanda ispisuje medijan po upitu i dodaje retke u `results\raw.csv`. Pojedinačni upiti: `--only Q1,Q4,S2`.
*Superset:* isključi cache grafikona (Database → Advanced → Chart cache timeout `-1`, ili ukloni Redis cache) – SQL Lab
upiti se ionako ne cachiraju. *Metabase:* cache je prema zadanim postavkama isključen (Admin → Performance).

## 4. Vrijeme crtanja u Supersetu i Metabaseu (preglednik)

Grafikone za svih 13 upita izradi automatski (isti SQL u oba alata), a URL-ovi se sami upišu u `config.json`:
```powershell
python make_charts.py all
python bench.py browser --tool superset
python bench.py browser --tool metabase
```
Metoda: Playwright (Chromium) otvori grafikon u čistom kontekstu, pronađe zahtjev za podacima (`data_url_contains`) i
mjeri vrijeme od **kraja odgovora s podacima** do **zadnje promjene DOM-a** (tišina `quiet_ms`).
`python make_compare.py` izrađuje usporedni grafikon (narudžbe po danu u tjednu) za potpoglavlje 5.7.

## 5. Power BI Desktop

1. *Get data → ClickHouse* (službeni konektor, ODBC upravljački program), host `localhost`, port `8123`, baza `instacart`,
   **DirectQuery**; učitaj svih 6 tablica.
2. Model: 5 relacija (*:1, *Assume referential integrity*) i mjere `COUNTROWS` (Broj proizvoda, Broj narudzbi,
   Broj stavki train, Broj stavki prior); stupce s ID-evima postavi na *Whole number*.
3. Jedna stranica = jedan stupčasti grafikon za upit (Q1-Q9, S1-S3; S4 = Q7). Upite generira Power BI iz modela.
4. *Optimize → Performance analyzer → Clear → Start recording → 6× Refresh visuals → Stop → Export* (`pbi_QX.json`).
5. `python parse_pbi.py pbi_QX.json --query QX` (prvo osvježavanje se odbacuje; `data_ms` = događaj *Query*,
   `render_ms` = *Render*, `server_ms` = *Execute Direct Query*).

## 6. Tableau Public

Tableau Public **nema** *Performance Recording* (postoji samo u Tableau Desktopu) i ograničen je na **15 M redaka po izvoru**,
pa radi nad CSV izvadcima; Q6-Q9 i S4 nisu izvedivi (n/p). Podskupovi za S1-S3:
```powershell
docker exec clickhouse clickhouse-client --password clickhouse123 -q "SELECT * FROM instacart.order_products_prior WHERE order_id <= 105000 INTO OUTFILE '/data/opp_S1.csv' FORMAT CSVWithNames"
```
(analogno 527000 → `opp_S2.csv`, 1055000 → `opp_S3.csv`). Za svaki upit: izradi list s grafikonom → 6× *Data → izvor → Refresh*
→ `python parse_tableau.py --query QX`. Skripta čita dnevnik `Documents/My Tableau Repository/Logs/log*.txt`:
`data_ms` = *compute-worksheet-data*, `render_ms` = *update-visual-model* − `data_ms`, `reload_ms` = cijelo osvježavanje.

## 7. Obrada

```powershell
python analyze.py
```
Stvara u `results\`: `summary.csv` (medijan, min, maks, kvartili, odstupanje), `table_*_ms.csv` (tablice za rad),
`fig_data_time.png`, `fig_render_time.png`, `fig_total_time.png`, `fig_scalability.png`, `fig_heatmap.png`,
`scores_auto.json` (ocjene za kriterije *Brzina* i *Skalabilnost* prema pravilima iz rada) i `consistency.txt`
(provjera da svi alati vraćaju isti rezultat po upitu).

**Pravila ocjenjivanja** (1–5): *Brzina* – geometrijska sredina omjera ukupnog vremena prema najbržem vizualizacijskom
alatu po upitu: ≤1,25 → 5; ≤1,75 → 4; ≤2,5 → 3; ≤4 → 2; inače 1. *Skalabilnost* – eksponent b pravca log(vrijeme) ~
log(broj redaka) kroz S1–S4: ≤0,6 → 5; ≤0,8 → 4; ≤1,0 → 3; ≤1,3 → 2; inače 1; alat koji ne može obraditi S4 (32,4 M) → 1.

## 8. Valjanost i ograničenja

- Mjerenja su na jednom računalu s Docker okruženjem; apsolutne vrijednosti ovise o hardveru, relativni odnosi su poanta.
- Alati se mjere različitim mehanizmima (REST API, preglednik, Performance Analyzer, Tableau Performance Recording);
  `data_ms` je „vrijeme dohvata iz perspektive alata“, ne identičan interni događaj.
- Tableau Public radi nad datotekama (ekstrakt), pa njegov `data_ms` nije izravno usporediv s alatima koji šalju upit bazi.
- Cache poslužitelja i OS-a: zagrijavanje je odbačeno, rezultati su „topli“; hladni start nije mjeren.
- Skripte `bench.py`/`analyze.py` testirane su na lažnim poslužiteljima (`tests/`); selektori i URL-ovi za preglednik
  mogu zahtijevati prilagodbu na tvojoj instalaciji.

## 9. Struktura repozitorija

```
olap-benchmark/
  bench.py  analyze.py  parse_pbi.py  queries.json  config.example.json
  manual_template.csv  requirements.txt  README.md  .gitignore
  results/  (raw.csv, sysinfo.json, scale_rows.json, summary.csv, table_*.csv, fig_*.png, scores_auto.json)
  tests/    (lažni poslužitelji za provjeru koda; brojke nisu stvarne)
```
Snimke zaslona usporednih vizualizacija i Performance Analyzera nalaze se u `results/screenshots/`.

Literatura: Microsoft Corporation (2026) *Use Performance Analyzer to examine report performance*; Tableau Software, LLC (2026)
*Create a Performance Recording*; Tableau Software, LLC (2026) *Tableau Desktop and Tableau Desktop Public Edition Feature Comparison*.
