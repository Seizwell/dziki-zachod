/*
 * Algorytm "Dziki Zachód" — rozproszone dobieranie w pary w sekcji krytycznej
 * o pojemności S. Implementacja OpenMPI w C++.
 *
 * Kompilacja:   mpic++ -O2 -o dziki_zachod dziki_zachod.cpp
 * Uruchomienie: mpirun -np N ./dziki_zachod S [max_rounds]
 */

#include <mpi.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdarg>
#include <vector>
#include <algorithm>
#include <unistd.h>

// ─── Kolory ANSI ────────────────────────────────────────────────
static const char* CL[] = {
    "\033[1;31m","\033[1;32m","\033[1;33m","\033[1;34m",
    "\033[1;35m","\033[1;36m","\033[1;91m","\033[1;92m",
    "\033[1;93m","\033[1;94m","\033[1;95m","\033[1;96m",
};
static const char* R = "\033[0m";
static const char* B = "\033[1m";

// ─── Stany, typy ────────────────────────────────────────────────
enum State { REST, WAIT_SALOON, IN_SALOON_FREE, IN_SALOON_WAITING, FIGHTING };
enum MsgType { MREQ=1, MACK=2, MLOOK=3, MPROP=4, MACC=5, MREJ=6 };
static const char* SN[] = {"REST","WAIT_SALOON","IN_SALOON_FREE","IN_SALOON_WAITING","FIGHTING"};

struct Msg { int from, prio, ref, type; };
static const int TAG = 42;

// ─── MPI helpers ────────────────────────────────────────────────
static void send_to(int to, MsgType t, int me, int p=0, int r=0) {
    Msg m = {me, p, r, (int)t};
    MPI_Send(&m, sizeof(Msg), MPI_BYTE, to, TAG, MPI_COMM_WORLD);
}
static void bcast(int n, int me, MsgType t, int p=0, int r=0) {
    for (int i=0; i<n; i++) if (i!=me) send_to(i, t, me, p, r);
}
static int drain(std::vector<Msg>& o) {
    int c=0;
    while (1) {
        int f=0; MPI_Status s;
        MPI_Iprobe(MPI_ANY_SOURCE, TAG, MPI_COMM_WORLD, &f, &s);
        if (!f) break;
        Msg m;
        MPI_Recv(&m, sizeof(Msg), MPI_BYTE, s.MPI_SOURCE, TAG, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        o.push_back(m); c++;
    }
    return c;
}

static void plog(int r, const char* s, const char* fmt, ...) {
    fprintf(stderr, "%s[P%d│%-18s]%s ", CL[r%12], r, s, R);
    va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a);
    fprintf(stderr, "\n");
}

// ═════════════════════════════════════════════════════════════════
int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);
    int rank, N;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &N);

    if (argc < 2) {
        if (!rank) fprintf(stderr, "Użycie: mpirun -np N %s S [max_rounds]\n", argv[0]);
        MPI_Finalize(); return 1;
    }
    int S = atoi(argv[1]);
    int max_rounds = (argc >= 3) ? atoi(argv[2]) : 5;
    if (S < 2 || S % 2 || S >= N) {
        if (!rank) fprintf(stderr, "Błąd: S=%d parzyste, >=2, <N=%d\n", S, N);
        MPI_Finalize(); return 1;
    }

    // ─── Zmienne lokalne ────────────────────────────────────────
    State state = REST;
    int clk = 0, my_prio = 0, ack_cnt = 0, rounds = 0;
    std::vector<int> waitQ;
    int cand = -1, partner = -1;
    int wait_ticks = 0;  // timeout na IN_SALOON_WAITING
    const int WAIT_TIMEOUT = 2000; // ~10s przy 50us/tick

    MPI_Barrier(MPI_COMM_WORLD);
    if (!rank) {
        fprintf(stderr, "\n%s═══════════════════════════════════════════════════%s\n", B, R);
        fprintf(stderr, "%s  🤠 DZIKI ZACHÓD — OpenMPI%s\n", B, R);
        fprintf(stderr, "  N=%s%d%s | S=%s%d%s | Rundy=%s%d%s\n",
                B,N,R, B,S,R, B,max_rounds,R);
        fprintf(stderr, "%s═══════════════════════════════════════════════════%s\n", B, R);
        for (int i=0; i<N; i++) fprintf(stderr, "  %s██ P%d%s", CL[i%12], i, R);
        fprintf(stderr, "\n\n");
    }
    MPI_Barrier(MPI_COMM_WORLD);
    usleep(rank * 2000);

    auto flush = [&]() {
        for (int w : waitQ) send_to(w, MACK, rank, 0, my_prio);
        waitQ.clear();
    };

    auto start_round = [&]() {
        clk++; my_prio = clk; ack_cnt = 0;
        cand = partner = -1; wait_ticks = 0;
        waitQ.clear();
        state = WAIT_SALOON;
        plog(rank, SN[state], "Runda %d → REQ(prio=%d)", rounds+1, my_prio);
        bcast(N, rank, MREQ, my_prio, 0);
    };

    start_round();

    // ─── Główna pętla ──────────────────────────────────────────
    int iter = 0;
    while (rounds < max_rounds && iter < 5000000) {
        iter++;
        std::vector<Msg> inbox;
        drain(inbox);

        for (auto& m : inbox) {
            int j = m.from;
            MsgType mt = (MsgType)m.type;
            clk = std::max(clk, m.prio) + 1;

            switch (state) {
            case REST:
                if (mt == MREQ) send_to(j, MACK, rank, 0, m.prio);
                break;

            case WAIT_SALOON:
                if (mt == MREQ) {
                    if (std::make_pair(m.prio, j) < std::make_pair(my_prio, rank))
                        send_to(j, MACK, rank, 0, m.prio);
                    else
                        waitQ.push_back(j);
                }
                else if (mt == MACK && m.ref == my_prio) {
                    ack_cnt++;
                    if (ack_cnt >= N - S) {
                        state = IN_SALOON_FREE;
                        plog(rank, SN[state], "Do salonu! (%d ACK) → LOOK", ack_cnt);
                        flush();
                        bcast(N, rank, MLOOK, 0, 0);
                    }
                }
                break;

            case IN_SALOON_FREE:
                if (mt == MREQ) {
                    send_to(j, MACK, rank, 0, m.prio);
                }
                else if (mt == MLOOK && rank > j) {
                    cand = j;
                    send_to(j, MPROP, rank, 0, 0);
                    state = IN_SALOON_WAITING;
                    wait_ticks = 0;
                    plog(rank, SN[state], "LOOK od P%d → PROP", j);
                }
                else if (mt == MPROP) {
                    partner = j;
                    send_to(j, MACC, rank, 0, 0);
                    flush();
                    state = FIGHTING;
                    plog(rank, SN[state], "PROP od P%d → ACC ⚔️", j);
                }
                break;

            case IN_SALOON_WAITING:
                if (mt == MREQ) {
                    send_to(j, MACK, rank, 0, m.prio);
                }
                else if (mt == MACC && cand == j) {
                    partner = j;
                    flush();
                    state = FIGHTING;
                    plog(rank, SN[state], "ACC od P%d → ⚔️", j);
                }
                else if (mt == MREJ && cand == j) {
                    cand = -1;
                    state = IN_SALOON_FREE;
                    plog(rank, SN[state], "REJ od P%d → szukam", j);
                    bcast(N, rank, MLOOK, 0, 0);
                }
                else if (mt == MPROP) {
                    send_to(j, MREJ, rank, 0, 0);
                    plog(rank, SN[state], "PROP od P%d → REJ", j);
                }
                break;

            case FIGHTING:
                if (mt == MREQ) waitQ.push_back(j);
                else if (mt == MPROP) send_to(j, MREJ, rank, 0, 0);
                break;
            }
        }

        // ── Timeout na IN_SALOON_WAITING ──
        if (state == IN_SALOON_WAITING) {
            wait_ticks++;
            if (wait_ticks >= WAIT_TIMEOUT) {
                plog(rank, SN[IN_SALOON_FREE], "Timeout! P%d nie odpowiada → szukam", cand);
                cand = -1;
                state = IN_SALOON_FREE;
                wait_ticks = 0;
                bcast(N, rank, MLOOK, 0, 0);
            }
        }

        // ── FIGHTING: kończymy ──
        if (state == FIGHTING) {
            usleep(15000);
            int w = std::max(rank, partner);
            plog(rank, SN[state], w == rank ? "🏆 WYGRAŁEM z P%d!" : "🏥 Przegrałem z P%d...", partner);
            rounds++;
            flush();
            if (rounds < max_rounds) start_round();
            else plog(rank, "DONE", "🎉 Wszystkie %d rund!", max_rounds);
        }

        if (inbox.empty() && state != FIGHTING) usleep(50);
    }

    MPI_Barrier(MPI_COMM_WORLD);
    if (!rank) {
        fprintf(stderr, "\n%s═══════════════════════════════════════════════════%s\n", B, R);
        fprintf(stderr, "%s  ✅ Symulacja zakończona!%s\n", B, R);
        fprintf(stderr, "  N=%d, S=%d, Rundy=%d, Iteracje=%d\n", N, S, max_rounds, iter);
        fprintf(stderr, "%s═══════════════════════════════════════════════════%s\n", B, R);
    }

    MPI_Finalize();
    return 0;
}
