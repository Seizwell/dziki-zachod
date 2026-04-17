"""
Algorytm "Dziki Zachód" — rozproszone dobieranie w pary w sekcji krytycznej o pojemności S.
Wykorzystuje rozszerzony algorytm Ricarta-Agrawali z zegarem Lamporta.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


# ─── Stany procesu ───────────────────────────────────────────────
class State(Enum):
    REST = "REST"
    WAIT_SALOON = "WAIT_SALOON"
    IN_SALOON_FREE = "IN_SALOON_FREE"
    IN_SALOON_WAITING = "IN_SALOON_WAITING"
    FIGHTING = "FIGHTING"


# ─── Typy wiadomości ─────────────────────────────────────────────
class MsgType(Enum):
    REQ_SALOON = "REQ_SALOON"
    ACK_SALOON = "ACK_SALOON"
    LOOKING = "LOOKING"
    PROPOSE = "PROPOSE"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass
class Message:
    msg_type: MsgType
    sender_id: int
    prio: Optional[int] = None       # REQ_SALOON
    req_prio: Optional[int] = None   # ACK_SALOON


class Mailbox:
    """Centralna skrzynka — symuluje kanał komunikacji."""

    def __init__(self):
        self.queues: dict[int, list[Message]] = {}

    def register(self, proc_id: int):
        self.queues[proc_id] = []

    def send(self, dest_id: int, msg: Message):
        self.queues[dest_id].append(msg)

    def receive(self, proc_id: int) -> Optional[Message]:
        q = self.queues[proc_id]
        return q.pop(0) if q else None


class Process:
    """Pojedynczy proces (rewolwerowiec)."""

    def __init__(self, proc_id: int, n: int, s: int, mailbox: Mailbox):
        self.id = proc_id
        self.n = n
        self.s = s
        self.mb = mailbox

        self.state = State.REST
        self.clock = 0
        self.my_prio: int = 0
        self.ack_count = 0
        self.wait_queue: list[int] = []
        self.candidate: Optional[int] = None
        self.partner_id: Optional[int] = None
        self.last_fight_partner: Optional[int] = None
        self.last_fight_winner: Optional[int] = None

        self.log: list[str] = []

    def _log(self, msg: str):
        self.log.append(f"[P{self.id} | {self.state.value}] {msg}")

    def _send(self, msg: Message, dest: int):
        self.mb.send(dest, msg)

    def _broadcast(self, msg: Message):
        for pid in range(self.n):
            if pid != self.id:
                self._send(msg, pid)

    def _tick(self):
        self.clock += 1

    def _tick_on_receive(self, other_clock: int):
        self.clock = max(self.clock, other_clock) + 1

    # ─── Akcje inicjujące ────────────────────────────────────────
    def action_rest_start(self):
        """Wejście w stan REST → wysyła REQ i przechodzi do WAIT_SALOON."""
        self._tick()
        self.my_prio = self.clock
        self.ack_count = 0
        self.candidate = None
        self.partner_id = None
        self.state = State.WAIT_SALOON
        self._log(f"REQ_SALOON(prio={self.my_prio}) → broadcast")
        self._broadcast(Message(MsgType.REQ_SALOON, self.id, prio=self.my_prio))

    def action_enter_salon(self):
        """Wchodzimy do salonu — wysyłamy LOOKING."""
        self.state = State.IN_SALOON_FREE
        self._log("Wchodzę do salonu → LOOKING broadcast")
        self._broadcast(Message(MsgType.LOOKING, self.id))

    def action_fight_start(self, partner: int):
        """Sparowani — walka!"""
        self.partner_id = partner
        winner = max(self.id, partner)
        self.last_fight_partner = partner
        self.last_fight_winner = winner
        self.state = State.FIGHTING
        self._log(f"FIGHT z P{partner} → {'WYGRANA' if winner == self.id else 'PRZEGRANA'}")

        # Zwolnij oczekujących
        for j in self.wait_queue:
            self._send(Message(MsgType.ACK_SALOON, self.id, req_prio=self.my_prio), j)
        self.wait_queue.clear()

    def action_fight_end(self):
        """Po walce — odpoczynek."""
        self.partner_id = None
        self.candidate = None
        self.state = State.REST
        self._log("Koniec walki → REST")

    # ─── Obsługa wiadomości ──────────────────────────────────────
    def handle(self, msg: Message):
        # Zegar Lamporta — aktualizuj przy każdej wiadomości
        recv_prio = msg.prio if msg.prio is not None else 0
        self._tick_on_receive(recv_prio)

        dispatch = {
            State.REST: self._on_rest,
            State.WAIT_SALOON: self._on_wait_saloon,
            State.IN_SALOON_FREE: self._on_free,
            State.IN_SALOON_WAITING: self._on_waiting,
            State.FIGHTING: self._on_fighting,
        }
        dispatch[self.state](msg)

    # REST
    def _on_rest(self, msg: Message):
        if msg.msg_type == MsgType.REQ_SALOON:
            self._send(Message(MsgType.ACK_SALOON, self.id, req_prio=msg.prio), msg.sender_id)
            self._log(f"REQ od P{msg.sender_id} → ACK")

    # WAIT_SALOON
    def _on_wait_saloon(self, msg: Message):
        if msg.msg_type == MsgType.REQ_SALOON:
            if (msg.prio, msg.sender_id) < (self.my_prio, self.id):
                self._send(Message(MsgType.ACK_SALOON, self.id, req_prio=msg.prio), msg.sender_id)
            else:
                self.wait_queue.append(msg.sender_id)
                self._log(f"REQ od P{msg.sender_id} → waitQueue")

        elif msg.msg_type == MsgType.ACK_SALOON:
            if msg.req_prio == self.my_prio:
                self.ack_count += 1
                self._log(f"ACK ({self.ack_count}/{self.n - self.s})")
                if self.ack_count >= self.n - self.s:
                    self._log("Wystarczająco ACK → do salonu!")
                    self.action_enter_salon()

    # IN_SALOON_FREE
    def _on_free(self, msg: Message):
        if msg.msg_type == MsgType.REQ_SALOON:
            self.wait_queue.append(msg.sender_id)

        elif msg.msg_type == MsgType.LOOKING:
            if self.id > msg.sender_id:
                self.candidate = msg.sender_id
                self._send(Message(MsgType.PROPOSE, self.id), msg.sender_id)
                self.state = State.IN_SALOON_WAITING
                self._log(f"LOOKING od P{msg.sender_id} → PROPOSE")
            # niższy ID czeka na PROPOSE

        elif msg.msg_type == MsgType.PROPOSE:
            self.partner_id = msg.sender_id
            self._send(Message(MsgType.ACCEPT, self.id), msg.sender_id)
            self._log(f"PROPOSE od P{msg.sender_id} → ACCEPT")
            self.action_fight_start(msg.sender_id)

    # IN_SALOON_WAITING
    def _on_waiting(self, msg: Message):
        if msg.msg_type == MsgType.REQ_SALOON:
            self.wait_queue.append(msg.sender_id)

        elif msg.msg_type == MsgType.ACCEPT:
            if self.candidate == msg.sender_id:
                self._log(f"ACCEPT od P{msg.sender_id} → walczymy!")
                self.action_fight_start(msg.sender_id)

        elif msg.msg_type == MsgType.REJECT:
            if self.candidate == msg.sender_id:
                self.candidate = None
                self.state = State.IN_SALOON_FREE
                self._log(f"REJECT od P{msg.sender_id} → szukam dalej")
                self._broadcast(Message(MsgType.LOOKING, self.id))

        elif msg.msg_type == MsgType.PROPOSE:
            self._send(Message(MsgType.REJECT, self.id), msg.sender_id)
            self._log(f"PROPOSE od P{msg.sender_id} → REJECT (negocjuję)")

    # FIGHTING
    def _on_fighting(self, msg: Message):
        if msg.msg_type == MsgType.REQ_SALOON:
            self.wait_queue.append(msg.sender_id)
        elif msg.msg_type == MsgType.PROPOSE:
            self._send(Message(MsgType.REJECT, self.id), msg.sender_id)


def run_simulation(n: int = 6, s: int = 2, max_rounds: int = 2, verbose: bool = True):
    assert s >= 2 and s % 2 == 0, "S musi być parzyste >= 2"
    assert n >= s, "N musi być >= S"

    mb = Mailbox()
    procs = [Process(i, n, s, mb) for i in range(n)]
    for p in procs:
        mb.register(p.id)

    round_count = {p.id: 0 for p in procs}
    fight_log: list[tuple[int, int, int]] = []

    # Wszyscy startują
    for p in procs:
        p.action_rest_start()

    fighting: set[int] = set()  # ID procesów w trakcie walki
    fight_ticks: dict[int, int] = {}

    for step in range(10000):
        # 1. Dostarcz WSZYSTKIE wiadomości (wiele rund, bo generują nowe)
        delivered = True
        while delivered:
            delivered = False
            for p in procs:
                msg = mb.receive(p.id)
                if msg:
                    p.handle(msg)
                    delivered = True

        # 2. Wykryj nowe walki
        for p in procs:
            if p.state == State.FIGHTING and p.id not in fighting:
                fighting.add(p.id)
                fight_ticks[p.id] = 3  # walka trwa 3 ticki

        # 3. Kończ walki po czasie
        done = [pid for pid, ticks in fight_ticks.items() if ticks <= 0]
        for pid in done:
            p = procs[pid]
            partner = p.last_fight_partner
            winner = p.last_fight_winner

            # Rejestruj walkę (od niższego ID, żeby uniknąć duplikatów)
            if partner is not None and pid < partner:
                fight_log.append((pid, partner, winner))

            p.action_fight_end()
            round_count[pid] += 1
            fighting.discard(pid)
            del fight_ticks[pid]

            if round_count[pid] < max_rounds:
                p.action_rest_start()

        # Tick walk
        for pid in list(fight_ticks):
            fight_ticks[pid] -= 1

        # 4. Koniec?
        if all(rc >= max_rounds for rc in round_count.values()):
            break

    # ─── Raport ──────────────────────────────────────────────────
    print("=" * 60)
    print(f"  ALGORYTM 'DZIKI ZACHÓD' — Symulacja")
    print(f"  N={n} procesów, S={s} pojemność salonu, {max_rounds} rund")
    print("=" * 60)

    print("\n📊 Wyniki walk:")
    for p1, p2, winner in fight_log:
        loser = p1 if winner == p2 else p2
        print(f"  P{p1} vs P{p2} → wygrał P{winner}, przegrał P{loser}")

    print(f"\n⚔️  Łącznie walk: {len(fight_log)}")

    if verbose:
        print("\n📋 Logi:")
        for p in procs:
            print(f"\n  === P{p.id} ({round_count[p.id]} rund) ===")
            for e in p.log:
                print(f"    {e}")

    print("\n" + "=" * 60)
    print(f"  ✅ Symulacja OK! ({step + 1} kroków)")
    print("=" * 60)


if __name__ == "__main__":
    print("🔧 Test 1: N=4, S=2\n")
    run_simulation(n=4, s=2, max_rounds=2)

    print("\n\n🔧 Test 2: N=6, S=2\n")
    run_simulation(n=6, s=2, max_rounds=2)

    print("\n\n🔧 Test 3: N=8, S=4\n")
    run_simulation(n=8, s=4, max_rounds=1)
