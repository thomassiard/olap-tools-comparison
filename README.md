# Analiza i usporedba OLAP alata

Fakultet: [Fakultet informatike u Puli](https://fipu.unipu.hr)\
Diplomski rad: [Diplomski rad]{https://fipu.unipu.hr/fipu/predmet/diprad_a}\
Mentor: [izv. prof. dr. sc. Goran Oreški](https://fipu.unipu.hr/fipu/en/goran.oreski)\
Student: Thomas Siard

U radu uspoređujem pet alata za analizu podataka na istom skupu podataka
([Instacart](https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis), 32 milijuna zapisa):

- **ClickHouse**, baza podataka
- **Apache Superset**
- **Metabase**
- **Power BI**
- **Tableau Public**

Svaki alat je izvršio istih 9 upita i 4 testa skalabilnosti, a vremena su mjerena više puta.

## Rezultati

Vrijeme do prikaza grafa, medijan u milisekundama:

| Upit | ClickHouse | Superset | Metabase | Power BI | Tableau |
|---|---:|---:|---:|---:|---:|
| Mali upit (Q1) | 11 | 447 | 203 | 199 | 46 |
| 32 M zapisa (Q8) | 279 | 723 | 544 | 493 | – |
| 32 M zapisa, 4 tablice (Q9) | 843 | 1.321 | 1.079 | 6.278 | – |

Tableau Public ne može učitati više od 15 milijuna redaka.
Svi rezultati i grafovi su u mapi [`olap-benchmark/results`](olap-benchmark/results).

## Sadržaj

| Mapa | Što je unutra |
|---|---|
| `olap-benchmark/` | skripte za mjerenje, upiti i rezultati |
| `data/` | SQL za učitavanje podataka u ClickHouse |
| `powerbi/`, `tableau/` | datoteke korištene za mjerenje |
| `docker-compose.yml` | pokreće ClickHouse, Superset i Metabase |

## Pokretanje

1. Preuzmi CSV datoteke s [Kagglea](https://www.kaggle.com/datasets/psparks/instacart-market-basket-analysis) u mapu `data/`
2. `docker compose up -d`
3. `docker exec -i clickhouse clickhouse-client --password clickhouse123 --multiquery < data/setup_instacart.sql`

Upute za mjerenje: [`olap-benchmark/README.md`](olap-benchmark/README.md)
