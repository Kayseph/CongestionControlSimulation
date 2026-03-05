# main.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from network import NetworkSimulator
from database import log_simulation_result
from report_generator import generate_report
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib import rcParams
from datetime import datetime
import threading
import os

# ══════════════════════════════════════════════════════════════════
#  COLOUR PALETTE  — dark terminal / network monitor aesthetic
# ══════════════════════════════════════════════════════════════════
BG       = "#0D1117"
PANEL    = "#161B22"
BORDER   = "#30363D"
TEXT     = "#E6EDF3"
TEXT_DIM = "#8B949E"
ACCENT   = "#58A6FF"
ACCENT2  = "#3FB950"
WARN     = "#D29922"
DANGER   = "#F85149"
PURPLE   = "#BC8CFF"

CHART_COLORS = ["#58A6FF","#3FB950","#F78166","#BC8CFF",
                "#D29922","#39C5CF","#FF7B72","#79C0FF"]

# ══════════════════════════════════════════════════════════════════
#  MATPLOTLIB DARK THEME
# ══════════════════════════════════════════════════════════════════
rcParams.update({
    "figure.facecolor": BG,    "axes.facecolor":  PANEL,
    "axes.edgecolor":   BORDER,"axes.labelcolor": TEXT_DIM,
    "axes.grid": True,         "grid.color":      BORDER,
    "grid.linestyle": "--",    "grid.alpha":      0.5,
    "xtick.color":  TEXT_DIM,  "ytick.color":     TEXT_DIM,
    "text.color":   TEXT,      "legend.facecolor":PANEL,
    "legend.edgecolor": BORDER,"legend.fontsize": 7,
    "lines.linewidth": 1.6,    "font.family":     "monospace",
    "font.size": 8,
})

# ══════════════════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════════════════
auto_run               = False
simulation_interval_ms = 5000
cumulative_runs        = []

# ══════════════════════════════════════════════════════════════════
#  WIDGET HELPERS
# ══════════════════════════════════════════════════════════════════
def _combo(parent, var, values, width=14):
    cb = ttk.Combobox(parent, textvariable=var, values=values,
                      width=width, state="readonly",
                      font=("Courier New", 9))
    return cb

def _btn(parent, text, command, color=ACCENT, width=22):
    b = tk.Button(parent, text=text, command=command,
                  bg=PANEL, fg=color, activebackground=color,
                  activeforeground=BG, relief="flat",
                  font=("Courier New", 9, "bold"),
                  width=width, padx=6, pady=6,
                  cursor="hand2", bd=0,
                  highlightthickness=1,
                  highlightbackground=color)
    b.bind("<Enter>", lambda e, c=color: b.config(bg=c, fg=BG))
    b.bind("<Leave>", lambda e, c=color: b.config(bg=PANEL, fg=c))
    return b

def _section_hdr(parent, text):
    tk.Label(parent, text=text, bg=PANEL, fg=TEXT_DIM,
             font=("Courier New", 7, "bold")).pack(anchor="w", padx=14, pady=(14,3))
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=10)

def _metric_row(parent, label, row):
    tk.Label(parent, text=label, bg=PANEL, fg=TEXT_DIM,
             font=("Courier New", 7)).grid(row=row, column=0, sticky="w", pady=3)
    val = tk.Label(parent, text="—", bg=PANEL, fg=TEXT_DIM,
                   font=("Courier New", 11, "bold"))
    val.grid(row=row, column=1, sticky="e", padx=(6,0))
    return val

# ══════════════════════════════════════════════════════════════════
#  SIMULATION LOGIC
# ══════════════════════════════════════════════════════════════════
def run_simulation():
    global cumulative_runs

    aqm    = aqm_var.get()
    sender = sender_var.get()
    flows  = int(flow_var.get())

    status_var.set("● RUNNING")
    status_lbl.config(fg=WARN)
    root.update_idletasks()

    sim     = NetworkSimulator(flows=flows, aqm_type=aqm, sender_type=sender)
    results = sim.run()

    run_record = {
        **results,
        "aqm":       aqm,
        "sender":    sender,
        "flows":     flows,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    cumulative_runs.append(run_record)

    _refresh_metrics(results)
    log_simulation_result(aqm, sender, flows,
                          results["throughput"], results["loss_rate"],
                          results["avg_queue"],  results["avg_delay"],
                          results["fairness"])
    update_plot()
    _refresh_counter()

    status_var.set("● IDLE")
    status_lbl.config(fg=ACCENT2)

    if auto_run:
        root.after(simulation_interval_ms, run_simulation)


def _refresh_metrics(r):
    tput_val.config( text=f"{r['throughput']:.1f}",
                     fg=ACCENT)
    loss_val.config( text=f"{r['loss_rate']:.4f}",
                     fg=DANGER if r['loss_rate'] > 0.05 else ACCENT2)
    queue_val.config(text=f"{r['avg_queue']:.1f}",
                     fg=WARN   if r['avg_queue'] > 40   else TEXT)
    delay_val.config(text=f"{r['avg_delay']:.4f}",
                     fg=WARN   if r['avg_delay'] > 0.1  else TEXT)
    fair_val.config( text=f"{r['fairness']:.4f}",
                     fg=ACCENT2 if r['fairness'] > 0.9  else WARN)
    aqmd = r.get("total_aqm_drops", 0)
    bufd = r.get("total_buf_drops",  0)
    aqmd_val.config(text=f"{aqmd:,}", fg=WARN   if aqmd > 0 else TEXT_DIM)
    bufd_val.config(text=f"{bufd:,}", fg=DANGER if bufd > 0 else TEXT_DIM)


def _refresh_counter():
    n = len(cumulative_runs)
    counter_var.set(f"{n} RUN{'S' if n != 1 else ''}  LOGGED")


def toggle_auto_run():
    global auto_run
    auto_run = not auto_run
    if auto_run:
        auto_btn.config(text="◼  STOP AUTO",
                        highlightbackground=DANGER, fg=DANGER)
        auto_btn.bind("<Enter>", lambda e: auto_btn.config(bg=DANGER,  fg=BG))
        auto_btn.bind("<Leave>", lambda e: auto_btn.config(bg=PANEL,   fg=DANGER))
        run_simulation()
    else:
        auto_btn.config(text="▶▶ AUTO RUN",
                        highlightbackground=ACCENT2, fg=ACCENT2)
        auto_btn.bind("<Enter>", lambda e: auto_btn.config(bg=ACCENT2, fg=BG))
        auto_btn.bind("<Leave>", lambda e: auto_btn.config(bg=PANEL,   fg=ACCENT2))


def reset_runs():
    global cumulative_runs
    cumulative_runs = []
    update_plot()
    _refresh_counter()
    for w in [tput_val,loss_val,queue_val,delay_val,fair_val,aqmd_val,bufd_val]:
        w.config(text="—", fg=TEXT_DIM)


# ══════════════════════════════════════════════════════════════════
#  EXPORT
# ══════════════════════════════════════════════════════════════════
def _do_export(output_dir):
    try:
        fp = generate_report(cumulative_runs, output_dir=output_dir)
        root.after(0, lambda: _export_done(fp))
    except Exception as e:
        root.after(0, lambda: messagebox.showerror("Export Error", str(e)))


def export_report():
    if not cumulative_runs:
        messagebox.showwarning("No Data", "Run at least one simulation first.")
        return
    d = filedialog.askdirectory(title="Save report to…")
    if not d: return
    export_btn.config(state="disabled", text="  GENERATING…")
    threading.Thread(target=_do_export, args=(d,), daemon=True).start()


def _export_done(fp):
    export_btn.config(state="normal", text="  EXPORT REPORT")
    if messagebox.askyesno("Report Ready", f"Saved:\n{fp}\n\nOpen now?"):
        os.startfile(fp) if os.name == "nt" else os.system(f'xdg-open "{fp}"')


# ══════════════════════════════════════════════════════════════════
#  CHARTS
# ══════════════════════════════════════════════════════════════════
def update_plot():
    specs = [
        (ax1, "throughput", "THROUGHPUT  (pkt/s)", ACCENT),
        (ax2, "loss",       "LOSS  RATIO",         DANGER),
        (ax3, "queue",      "QUEUE  LENGTH",        WARN),
        (ax4, "delay",      "QUEUE  DELAY  (s)",    PURPLE),
    ]
    for ax, key, title, color in specs:
        ax.clear()
        ax.set_title(title, color=color, fontsize=7.5,
                     fontfamily="monospace", fontweight="bold", pad=5)
        ax.tick_params(labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER)
        ax.spines["bottom"].set_color(BORDER)

        for i, run in enumerate(cumulative_runs):
            ts    = run["time_series"]
            c     = CHART_COLORS[i % len(CHART_COLORS)]
            label = f"R{i+1} {run['aqm']}/{run['sender']}"
            ax.plot(ts["time"], ts[key], color=c,
                    label=label, linewidth=1.5, alpha=0.9)

        if cumulative_runs:
            ax.legend(loc="upper right", fontsize=6.5,
                      framealpha=0.7, borderpad=0.5)

    fig.tight_layout(pad=2.2)
    canvas.draw()


# ══════════════════════════════════════════════════════════════════
#  BUILD ROOT
# ══════════════════════════════════════════════════════════════════
root = tk.Tk()
root.title("Congestion Control Simulator")
root.geometry("1220x840")
root.configure(bg=BG)
root.resizable(True, True)

# ttk style
sty = ttk.Style(root)
sty.theme_use("clam")
sty.configure(".",          background=PANEL, foreground=TEXT, bordercolor=BORDER,
               fieldbackground=BG, selectbackground=ACCENT, selectforeground=BG)
sty.configure("TCombobox",  background=PANEL, fieldbackground=BG,
               foreground=TEXT, arrowcolor=ACCENT)
sty.map("TCombobox", fieldbackground=[("readonly", BG)],
                     foreground=[("readonly", TEXT)])

# ── TITLE BAR ─────────────────────────────────────────────────────
title_bar = tk.Frame(root, bg=PANEL, height=52)
title_bar.pack(fill="x")
title_bar.pack_propagate(False)

tk.Label(title_bar,
         text="▣  CONGESTION  CONTROL  SIMULATOR",
         bg=PANEL, fg=ACCENT,
         font=("Courier New", 14, "bold")).pack(side="left", padx=20, pady=14)

tk.Label(title_bar,
         text="TCP · AQM · NETWORK ANALYSIS",
         bg=PANEL, fg=BORDER,
         font=("Courier New", 8)).pack(side="left", padx=0, pady=18)

counter_var = tk.StringVar(value="0 RUNS LOGGED")
tk.Label(title_bar, textvariable=counter_var,
         bg=PANEL, fg=TEXT_DIM,
         font=("Courier New", 9)).pack(side="right", padx=16)

status_var = tk.StringVar(value="● IDLE")
status_lbl = tk.Label(title_bar, textvariable=status_var,
                      bg=PANEL, fg=ACCENT2,
                      font=("Courier New", 9, "bold"))
status_lbl.pack(side="right", padx=6)

tk.Frame(root, bg=BORDER, height=1).pack(fill="x")

# ── BODY ──────────────────────────────────────────────────────────
body = tk.Frame(root, bg=BG)
body.pack(fill="both", expand=True)

# ── LEFT SIDEBAR ──────────────────────────────────────────────────
sidebar = tk.Frame(body, bg=PANEL, width=230)
sidebar.pack(side="left", fill="y", padx=(8,4), pady=8)
sidebar.pack_propagate(False)

# CONFIGURATION
_section_hdr(sidebar, "  CONFIGURATION")

cfg = tk.Frame(sidebar, bg=PANEL)
cfg.pack(fill="x", padx=14, pady=6)
cfg.columnconfigure(0, weight=1)

aqm_var    = tk.StringVar(value="RED")
sender_var = tk.StringVar(value="RENO")
flow_var   = tk.StringVar(value="4")

for i, (lbl, var, vals) in enumerate([
    ("AQM ALGORITHM",  aqm_var,    ["RED","ARED","NLRED","DropTail"]),
    ("SENDER TYPE",    sender_var, ["RENO","BBR"]),
    ("FLOW COUNT",     flow_var,   ["2","4","6","8"]),
]):
    tk.Label(cfg, text=lbl, bg=PANEL, fg=TEXT_DIM,
             font=("Courier New", 7)).grid(row=i*2,   column=0, sticky="w", pady=(7,1))
    _combo(cfg, var, vals).grid(row=i*2+1, column=0, sticky="ew", pady=(0,2))

# CONTROLS
_section_hdr(sidebar, "  CONTROLS")

ctrl = tk.Frame(sidebar, bg=PANEL)
ctrl.pack(fill="x", padx=10, pady=6)

_btn(ctrl, "▶  RUN SIMULATION", run_simulation, ACCENT).pack(fill="x", pady=3)

auto_btn = _btn(ctrl, "▶▶ AUTO RUN", toggle_auto_run, ACCENT2)
auto_btn.pack(fill="x", pady=3)

_btn(ctrl, "↺  RESET  GRAPHS", reset_runs, TEXT_DIM).pack(fill="x", pady=3)

# EXPORT
_section_hdr(sidebar, "  EXPORT")

exp = tk.Frame(sidebar, bg=PANEL)
exp.pack(fill="x", padx=10, pady=6)

export_btn = _btn(exp, "  EXPORT REPORT", export_report, PURPLE)
export_btn.pack(fill="x", pady=3)

# METRICS
_section_hdr(sidebar, "  LAST RUN  METRICS")

mf = tk.Frame(sidebar, bg=PANEL)
mf.pack(fill="x", padx=14, pady=6)
mf.columnconfigure(0, weight=1)
mf.columnconfigure(1, weight=0)

tput_val  = _metric_row(mf, "THROUGHPUT  pkt/s", 0)
loss_val  = _metric_row(mf, "LOSS  RATE",         1)
queue_val = _metric_row(mf, "AVG  QUEUE   pkts",  2)
delay_val = _metric_row(mf, "AVG  DELAY   s",     3)
fair_val  = _metric_row(mf, "FAIRNESS  INDEX",    4)

tk.Frame(mf, bg=BORDER, height=1).grid(
    row=5, column=0, columnspan=2, sticky="ew", pady=6)

aqmd_val = _metric_row(mf, "AQM  DROPS",   6)
bufd_val = _metric_row(mf, "BUF  DROPS",   7)

# footer
tk.Label(sidebar, text="v2.0  ·  CongestionSim",
         bg=PANEL, fg=BORDER,
         font=("Courier New", 7)).pack(side="bottom", pady=10)

# ── RIGHT CHART AREA ──────────────────────────────────────────────
chart_wrap = tk.Frame(body, bg=BG)
chart_wrap.pack(side="left", fill="both", expand=True, padx=(4,8), pady=8)

chart_hdr = tk.Frame(chart_wrap, bg=PANEL, height=34)
chart_hdr.pack(fill="x", pady=(0,5))
chart_hdr.pack_propagate(False)
tk.Label(chart_hdr,
         text="  REAL-TIME  SIMULATION  CHARTS",
         bg=PANEL, fg=TEXT_DIM,
         font=("Courier New", 8, "bold")).pack(side="left", padx=14, pady=9)

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(10.5, 6.8))
fig.patch.set_facecolor(BG)

canvas = FigureCanvasTkAgg(fig, master=chart_wrap)
canvas.get_tk_widget().configure(bg=BG, highlightthickness=0)
canvas.get_tk_widget().pack(fill="both", expand=True)

update_plot()

root.mainloop()
