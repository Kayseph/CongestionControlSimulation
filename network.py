# network.py

import random

# ===============================
# SIMULATION CONSTANTS
# ===============================
PACKET_SIZE_BITS  = 12000
LINK_CAPACITY_BPS = 10_000_000
STEP              = 0.1
SIM_TIME          = 60
BUFFER_SIZE       = 100
CAPACITY_PER_STEP = int((LINK_CAPACITY_BPS / PACKET_SIZE_BITS) * STEP)  # 83

INTER_ARRIVAL_MIN = 0.05
INTER_ARRIVAL_MAX = 0.15

PHASE_SLOW_START = "Slow Start"
PHASE_CONG_AVOID = "Congestion Avoidance"
PHASE_RECOVERY   = "Recovery"
PHASE_BBR_PBW    = "Probe BW"
PHASE_BBR_PRT    = "Probe RTT"


def jain_index(values):
    n  = len(values)
    s  = sum(values)
    sq = sum(v ** 2 for v in values)
    return (s ** 2) / (n * sq) if sq else 0


# ── AQM ──────────────────────────────────────────────────────────────────────
class RED:
    def __init__(self, min_th=20, max_th=60, max_p=0.1):
        self.min_th = min_th
        self.max_th = max_th
        self.max_p  = max_p
        self.avg    = 0.0
        self.wq     = 0.002

    def _update(self, q):
        self.avg = (1 - self.wq) * self.avg + self.wq * q

    def drop(self, q):
        self._update(q)
        if self.avg < self.min_th:  return False
        if self.avg >= self.max_th: return True
        return random.random() < self.max_p * (self.avg - self.min_th) / (self.max_th - self.min_th)

    @property
    def drop_prob(self):
        if self.avg < self.min_th:  return 0.0
        if self.avg >= self.max_th: return 1.0
        return self.max_p * (self.avg - self.min_th) / (self.max_th - self.min_th)


class ARED(RED):
    def drop(self, q):
        self._update(q)
        if self.avg > self.max_th:   self.max_p = min(0.5,  self.max_p + 0.005)
        elif self.avg < self.min_th: self.max_p = max(0.01, self.max_p - 0.002)
        if self.avg < self.min_th:  return False
        if self.avg >= self.max_th: return True
        return random.random() < self.max_p * (self.avg - self.min_th) / (self.max_th - self.min_th)


class NLRED(RED):
    def drop(self, q):
        self._update(q)
        if self.avg < self.min_th:  return False
        if self.avg >= self.max_th: return True
        ratio = (self.avg - self.min_th) / (self.max_th - self.min_th)
        return random.random() < self.max_p * (ratio ** 2)

    @property
    def drop_prob(self):
        if self.avg < self.min_th:  return 0.0
        if self.avg >= self.max_th: return 1.0
        ratio = (self.avg - self.min_th) / (self.max_th - self.min_th)
        return self.max_p * (ratio ** 2)


# ── Senders ───────────────────────────────────────────────────────────────────
class RenoSender:
    def __init__(self, flow_id=0):
        self.flow_id       = flow_id
        self.cwnd          = 2
        self.ssthresh      = 32
        self.phase         = PHASE_SLOW_START
        self.cwnd_history  = []
        self.phase_history = []

    def send(self):     return max(1, min(int(self.cwnd), 20))

    def on_ack(self):
        if self.cwnd < self.ssthresh:
            self.cwnd  = min(self.cwnd * 2, self.ssthresh + 1)
            self.phase = PHASE_SLOW_START
        else:
            self.cwnd += 1
            self.phase = PHASE_CONG_AVOID

    def on_loss(self):
        self.ssthresh = max(2, int(self.cwnd * 0.5))
        self.cwnd     = self.ssthresh
        self.phase    = PHASE_RECOVERY

    def record(self):
        self.cwnd_history.append(round(self.cwnd, 2))
        self.phase_history.append(self.phase)


class BBRSender:
    def __init__(self, flow_id=0):
        self.flow_id       = flow_id
        self.btlbw         = 5.0
        self.rtprop        = 0.02
        self.pacing_rate   = 8.0
        self.phase         = PHASE_BBR_PBW
        self._probe_rt_cd  = 0
        self.cwnd_history  = []
        self.phase_history = []

    def send(self):     return max(1, min(int(self.pacing_rate), 20))

    def update(self, delivered, rtt):
        if delivered > 0:
            self.btlbw = 0.9 * self.btlbw + 0.1 * (delivered / STEP)
        self.rtprop      = min(self.rtprop, rtt)
        self.pacing_rate = max(1.0, self.btlbw * self.rtprop * 10)
        self._probe_rt_cd += 1
        self.phase = PHASE_BBR_PRT if self._probe_rt_cd > 80 else PHASE_BBR_PBW
        if self._probe_rt_cd > 80:
            self._probe_rt_cd = 0

    def record(self):
        self.cwnd_history.append(round(self.pacing_rate, 2))
        self.phase_history.append(self.phase)


# ── Simulator ─────────────────────────────────────────────────────────────────
class NetworkSimulator:
    def __init__(self, flows=4, aqm_type="RED", sender_type="RENO"):
        self.time        = 0.0
        self.queue       = 0
        self.flows       = flows
        self.aqm_type    = aqm_type
        self.sender_type = sender_type

        self.total_queue     = 0
        self.total_sent      = 0
        self.total_dropped   = 0
        self.total_delivered = 0
        self.total_delay     = 0.0

        self.h_time      = []
        self.h_queue     = []
        self.h_tput      = []
        self.h_loss      = []
        self.h_delay     = []
        self.h_arrivals  = []
        self.h_aqm_avg   = []
        self.h_aqm_dp    = []
        self.h_aqm_drops = []
        self.h_buf_drops = []

        # Aggregates used directly by narrative — no dependency on event log
        self.total_aqm_drops = 0
        self.total_buf_drops = 0
        self.first_aqm_time  = None
        self.first_buf_time  = None
        self.first_rec_time  = None

        self.events = []   # (time, type, detail) — for Congestion Story sheet

        self.next_pkt_time = [random.uniform(0, 0.3) for _ in range(flows)]

        if aqm_type == "ARED":   self.aqm = ARED(min_th=20, max_th=60)
        elif aqm_type == "NLRED": self.aqm = NLRED(min_th=20, max_th=60)
        elif aqm_type == "RED":   self.aqm = RED(min_th=20, max_th=60)
        else:                     self.aqm = None   # DropTail

        self.senders = [
            (BBRSender if sender_type == "BBR" else RenoSender)(flow_id=i)
            for i in range(flows)
        ]

    def step(self):
        arrivals = aqm_drops = buf_drops = 0
        t = round(self.time, 2)

        for i, s in enumerate(self.senders):
            if self.time >= self.next_pkt_time[i]:
                pkts = s.send()
                arrivals += pkts
                self.total_sent += pkts
                self.next_pkt_time[i] = self.time + random.uniform(INTER_ARRIVAL_MIN, INTER_ARRIVAL_MAX)

        for _ in range(arrivals):
            if self.queue >= BUFFER_SIZE:
                buf_drops += 1
            elif self.aqm and self.aqm.drop(self.queue):
                aqm_drops += 1
            else:
                self.queue += 1

        dropped = aqm_drops + buf_drops
        self.total_dropped   += dropped
        self.total_aqm_drops += aqm_drops
        self.total_buf_drops += buf_drops

        # Track first-occurrence times for narrative
        if aqm_drops > 0 and self.first_aqm_time is None:
            self.first_aqm_time = t
        if buf_drops > 0 and self.first_buf_time is None:
            self.first_buf_time = t

        # Events for Congestion Story sheet (throttled to keep sheet readable)
        if buf_drops > 0:
            last = next((e for e in reversed(self.events) if e[1] == "BUFFER_FULL"), None)
            if not last or (t - last[0]) > 1.0:
                self.events.append((t, "BUFFER_FULL",
                    f"Buffer overflow: {buf_drops} pkt(s) dropped (queue={self.queue})"))

        if aqm_drops > 0:
            last = next((e for e in reversed(self.events) if e[1] == "AQM_DROP"), None)
            avg_q = getattr(self.aqm, 'avg', float(self.queue))
            if not last or (t - last[0]) > 0.5:
                self.events.append((t, "AQM_DROP",
                    f"{self.aqm_type} dropped {aqm_drops} pkt(s) "
                    f"(avg_q={avg_q:.1f}, drop_p={self.aqm.drop_prob:.3f})"))

        transmitted        = min(self.queue, CAPACITY_PER_STEP)
        self.queue        -= transmitted
        self.total_delivered += transmitted
        queue_delay        = self.queue / (CAPACITY_PER_STEP + 1e-9)
        rtt                = 0.02 + queue_delay
        self.total_delay  += rtt * transmitted

        for s in self.senders:
            prev = s.phase
            if isinstance(s, RenoSender):
                s.on_loss() if dropped > 0 else s.on_ack()
            else:
                s.update(transmitted, rtt)
            if s.phase != prev:
                cwnd_now = s.cwnd_history[-1] if s.cwnd_history else "?"
                self.events.append((t, "PHASE_CHANGE",
                    f"Flow {s.flow_id} ({self.sender_type}): {prev} → {s.phase} (cwnd≈{cwnd_now})"))
            s.record()

        prev_q = self.h_queue[-1] if self.h_queue else 0
        if self.queue < 10 and dropped == 0 and prev_q >= 20:
            self.events.append((t, "QUEUE_RECOVERED", f"Queue recovered to {self.queue} pkts"))
            if self.first_rec_time is None:
                self.first_rec_time = t

        self.total_queue += self.queue
        self.time = round(self.time + STEP, 2)

        avg_q = getattr(self.aqm, 'avg', float(self.queue)) if self.aqm else float(self.queue)
        dp    = self.aqm.drop_prob if self.aqm else (1.0 if self.queue >= BUFFER_SIZE else 0.0)

        self.h_time.append(self.time)
        self.h_queue.append(self.queue)
        self.h_tput.append(transmitted / STEP)
        self.h_loss.append(dropped / (arrivals + 1e-9))
        self.h_delay.append(rtt)
        self.h_arrivals.append(arrivals)
        self.h_aqm_avg.append(round(avg_q, 2))
        self.h_aqm_dp.append(round(dp, 4))
        self.h_aqm_drops.append(aqm_drops)
        self.h_buf_drops.append(buf_drops)

    def run(self, duration=SIM_TIME):
        while self.time < duration:
            self.step()

        steps      = duration / STEP
        throughput = self.total_delivered / duration
        loss_rate  = self.total_dropped / self.total_sent if self.total_sent else 0
        avg_queue  = self.total_queue / steps
        avg_delay  = self.total_delay / self.total_delivered if self.total_delivered else 0
        fairness   = jain_index([throughput / self.flows] * self.flows)

        # Phase-change counts for narrative
        reno_recoveries = [e for e in self.events if e[1]=="PHASE_CHANGE" and "Recovery" in e[2]]
        reno_ca         = [e for e in self.events if e[1]=="PHASE_CHANGE" and "Avoidance" in e[2]]

        return {
            "throughput":  throughput,
            "loss_rate":   loss_rate,
            "avg_queue":   avg_queue,
            "avg_delay":   avg_delay,
            "fairness":    fairness,
            # ── these are read directly by the narrative ──────────────────────
            "total_aqm_drops":  self.total_aqm_drops,
            "total_buf_drops":  self.total_buf_drops,
            "first_aqm_time":   self.first_aqm_time,
            "first_buf_time":   self.first_buf_time,
            "first_rec_time":   self.first_rec_time,
            "reno_recoveries":  len(reno_recoveries),
            "first_recovery_t": reno_recoveries[0][0] if reno_recoveries else None,
            "reno_ca_count":    len(reno_ca),
            # ── time-series for Congestion Story sheet ────────────────────────
            "time_series": {
                "time":          self.h_time,
                "queue":         self.h_queue,
                "throughput":    self.h_tput,
                "loss":          self.h_loss,
                "delay":         self.h_delay,
                "arrivals":      self.h_arrivals,
                "aqm_avg_queue": self.h_aqm_avg,
                "aqm_drop_prob": self.h_aqm_dp,
                "aqm_drops":     self.h_aqm_drops,
                "buffer_drops":  self.h_buf_drops,
            },
            "sender_histories": [
                {"flow_id": s.flow_id, "sender_type": self.sender_type,
                 "cwnd": s.cwnd_history, "phase": s.phase_history}
                for s in self.senders
            ],
            "events": self.events,
        }
