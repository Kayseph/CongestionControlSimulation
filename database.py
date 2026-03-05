# database.py

import pyodbc
from datetime import datetime

def get_connection():
    try:
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=localhost\\SQLEXPRESS;"
            "DATABASE=CongestionSimulator;"
            "Trusted_Connection=yes;"
        )
        return conn
    except Exception as e:
        print("Database connection failed:", e)
        return None

def log_simulation_result(aqm, sender, flows,
                          throughput, loss_rate,
                          avg_queue, avg_delay, fairness):
    conn = get_connection()
    if not conn:
        print("Cannot log simulation: No database connection")
        return

    cursor = conn.cursor()
    timestamp = datetime.now()
    try:
        cursor.execute("""
            INSERT INTO SimulationResults
            (Timestamp, AQM, SenderType, NumFlows,
             Throughput, LossRate, AvgQueue,
             AvgDelay, Fairness)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            timestamp,
            aqm,
            sender,
            flows,
            throughput,
            loss_rate,
            avg_queue,
            avg_delay,
            fairness
        )
        conn.commit()
        print(f"Simulation logged at {timestamp}")
    except Exception as e:
        print("Failed to log simulation:", e)
    finally:
        cursor.close()
        conn.close()
