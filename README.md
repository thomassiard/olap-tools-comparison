# Analiza i usporedba OLAP alata

Fakultet: [Fakultet informatike u Puli](https://fipu.unipu.hr)\
Kolegij: [Diplomski rad](https://fipu.unipu.hr/fipu/predmet/diprad_a)\
Mentor: [izv. prof. dr. sc. Goran Oreški](https://fipu.unipu.hr/fipu/en/goran.oreski)\
Student: Thomas Siard

Diplomski rad koji analizira i uspoređuje pet OLAP alata nad istim skupom podataka (Instacart, 3,4 M narudžbi i 32,4 M stavki):
**ClickHouse** (baza, osnovna linija), **Apache Superset**, **Metabase**, **Microsoft Power BI** i **Tableau Public**.
Alati se ocjenjuju prema devet kriterija (K1-K9: povezivanje, postavljanje, brzina, vizualizacije, jednostavnost,
licenciranje, dijeljenje, skalabilnost, dokumentacija), a brzina i skalabilnost se **mjere** nizom od 9 upita (Q1-Q9) i
4 koraka rastućeg obujma (S1-S4), s ponovljenim pokretanjima, u svih pet alata.

## Sažetak rezultata (medijan ukupnog vremena do prikaza, ms)

| Upit | ClickHouse | Superset | Metabase | Power BI | Tableau Public |
|---|---|---|---|---|---|
| Q1 mali filtar | 11 | 447 | 203 | 199 | 46 |
| Q5 spajanje 3 tablice | 33 | 487 | 296 | 208 | 134 |
| Q8 32,4 M, 3 tablice | 279 | 723 | 544 | 493 | n/p |
| Q9 32,4 M, 4 tablice | 843 | 1.321 | 1.079 | 6.278 | n/p |

n/p = Tableau Public ne može učitati izvor veći od 15 M redaka. Svi grafikoni i tablice: `olap-benchmark/results/`.

## Struktura repozitorija

```
docker-compose.yml        ClickHouse, Apache Superset i Metabase u Dockeru
data/                     SQL za izradu sheme i učitavanje CSV-ova (setup_instacart.sql), izvoz za Tableau
olap-benchmark/           skripte za mjerenje i obradu, upiti (queries.json), sirovi rezultati i grafikoni
powerbi/                  Power BI izvještaj korišten za mjerenje (DirectQuery, 12 stranica)
tableau/                  Tableau Public radna knjiga korištena za mjerenje
```

## Ponavljanje istraživanja

1. Preuzmi skup podataka s Kaggla: https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis
   (CSV datoteke nisu u repozitoriju jer prelaze GitHubovo ograničenje od 100 MB po datoteci) i raspakiraj ih u `data/`.
2. `docker compose up -d`
3. Učitaj podatke: `docker exec -i clickhouse clickhouse-client --password clickhouse123 --multiquery < data/setup_instacart.sql`
4. Provjera: `SELECT count() FROM instacart.order_products_prior` mora vratiti 32.434.489.
5. Mjerenje i obrada: upute u [`olap-benchmark/README.md`](olap-benchmark/README.md).

## Dataset

🔗 [https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis](https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis)
