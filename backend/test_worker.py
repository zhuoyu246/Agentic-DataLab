import pandas as pd
import subprocess
import sys
import os
import json
import uuid

parquet_path = r"C:\baidunetdiskdownload\master\agentdata\Agentic-DataLab\backend\storage\cold\default\cleaned_d1c3fb3913.parquet"
pkl_path = "test_input.pkl"
output_path = "test_output.json"

df = pd.read_parquet(parquet_path)
df.to_pickle(pkl_path)

print(f"Data shape: {df.shape}")
target = "cancer_status" # Make sure to use a valid column if it exists. We'll just pick the last column as a guess.
target = df.columns[-1]
print(f"Target: {target}")

args = [
    sys.executable,
    "agents/h2o_worker.py",
    "--input", pkl_path,
    "--output", output_path,
    "--target", target,
    "--run-id", uuid.uuid4().hex,
    "--max-runtime-seconds", "15",
    "--max-models", "2",
    "--mlflow-experiment-name", "Test_H2O"
]

env = os.environ.copy()
print("Running worker...")
try:
    proc = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    print("STDOUT:", proc.stdout)
    print("STDERR:", proc.stderr)
    print("Return code:", proc.returncode)
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            print("OUTPUT:", json.load(f))
except Exception as e:
    print("Failed:", e)
