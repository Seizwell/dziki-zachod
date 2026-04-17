# Dziki Zachód — Algorytm Rozproszonego Dobierania w Pary

Rozproszony algorytm dobierania procesów w pary w sekcji krytycznej o pojemności S, wykorzystujący rozszerzony algorytm Ricarta-Agrawali z zegarem Lamporta.

## Opis

Procesy (rewolwerowcy) rywalizują o wejście do **salonu** — rozproszonej sekcji krytycznej o pojemności `S`. Po wejściu do salonu dobierają się w pary poprzez 3-etapowy handshake:

1. **LOOKING** — rozgłoszenie "szukam partnera"
2. **PROPOSE** — propozycja walki od procesu o wyższym ID
3. **ACCEPT/REJECT** — jawna zgoda lub odrzucenie

Priorytet wejścia do salonu: zegar Lamporta (niższy = wyższy priorytet), remisy rozstrzyga niższe ID.

## Stany procesów

| Stan | Opis |
|------|------|
| `REST` | Odpoczynek (stan początkowy, po wygranej lub po powrocie ze szpitala) |
| `WAIT_SALOON` | Ubiega się o wejście do salonu |
| `IN_SALOON_FREE` | W salonie, szuka partnera |
| `IN_SALOON_WAITING` | Wysłał PROPOSE, czeka na odpowiedź |
| `FIGHTING` | Sparowany — odbywa pojedynek |

## Uruchomienie

```bash
python3 dziki_zachod.py
```

## Parametry

- `N` — liczba procesów (rewolwerowców)
- `S` — pojemność salonu (parzysta, ≥ 2)
- `max_rounds` — liczba rund walki na proces
