# server.py  — Flask backend for Congestion Control Simulator
from flask import Flask, jsonify, request, send_from_directory, send_file
import sys, os, json, tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from network import NetworkSimulator
from report_generator import generate_report

app = Flask(__name__, static_folder=".")

# In-memory run store (same role as cumulative_runs in main.py)
_runs = []

# ── serve the frontend ────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "index.html")

# ── run a single simulation ───────────────────────────────────────
@app.route("/api/run", methods=["POST"])
def api_run():
    body   = request.get_json()
    aqm    = body.get("aqm",    "RED")
    sender = body.get("sender", "RENO")
    flows  = int(body.get("flows", 4))

    sim     = NetworkSimulator(flows=flows, aqm_type=aqm, sender_type=sender)
    results = sim.run()

    record = {
        **results,
        "aqm":       aqm,
        "sender":    sender,
        "flows":     flows,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_id":    len(_runs) + 1,
    }
    _runs.append(record)

    # Return everything the UI needs
    return jsonify({
        "run_id":           record["run_id"],
        "aqm":              aqm,
        "sender":           sender,
        "flows":            flows,
        "timestamp":        record["timestamp"],
        "throughput":       round(results["throughput"],  2),
        "loss_rate":        round(results["loss_rate"],   4),
        "avg_queue":        round(results["avg_queue"],   2),
        "avg_delay":        round(results["avg_delay"],   4),
        "fairness":         round(results["fairness"],    4),
        "total_aqm_drops":  results.get("total_aqm_drops", 0),
        "total_buf_drops":  results.get("total_buf_drops", 0),
        "first_aqm_time":   results.get("first_aqm_time"),
        "reno_recoveries":  results.get("reno_recoveries", 0),
        "time_series":      results["time_series"],
    })

# ── get all runs summary ──────────────────────────────────────────
@app.route("/api/runs", methods=["GET"])
def api_runs():
    summary = []
    for r in _runs:
        summary.append({
            "run_id":          r["run_id"],
            "aqm":             r["aqm"],
            "sender":          r["sender"],
            "flows":           r["flows"],
            "timestamp":       r["timestamp"],
            "throughput":      round(r["throughput"],  2),
            "loss_rate":       round(r["loss_rate"],   4),
            "avg_queue":       round(r["avg_queue"],   2),
            "avg_delay":       round(r["avg_delay"],   4),
            "fairness":        round(r["fairness"],    4),
            "total_aqm_drops": r.get("total_aqm_drops", 0),
            "total_buf_drops": r.get("total_buf_drops", 0),
        })
    return jsonify(summary)

# ── reset all runs ────────────────────────────────────────────────
@app.route("/api/reset", methods=["POST"])
def api_reset():
    _runs.clear()
    return jsonify({"status": "ok"})

# ── export excel report ───────────────────────────────────────────
@app.route("/api/export", methods=["POST"])
def api_export():
    if not _runs:
        return jsonify({"error": "No runs to export"}), 400
    tmp = tempfile.mkdtemp()
    fp  = generate_report(_runs, output_dir=tmp)
    return send_file(fp, as_attachment=True,
                     download_name=os.path.basename(fp),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    print("\n  ▣  Congestion Control Simulator")
    print("  ──────────────────────────────────")
    print("  Open: http://localhost:5050\n")
   import os
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)), debug=False)
