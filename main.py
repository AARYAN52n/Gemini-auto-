import subprocess
import time
import os
import sys

print("=" * 60)
print("Gemini Claimer - Starting All Scripts")
print("=" * 60)

# Current folder ki saari .py files nikal lo (main.py ko chhod ke)
scripts = [f for f in os.listdir(".") if f.endswith(".py") and f != "main.py"]

if not scripts:
    print("Koi .py file nahi mili!")
    sys.exit()

print(f"\nTotal scripts mili: {len(scripts)}")
for s in scripts:
    print(f"  → {s}")

print("\nStarting all scripts...\n")

processes = []

for script in scripts:
    try:
        print(f"Starting: {script}")
        p = subprocess.Popen([sys.executable, script])
        processes.append((script, p))
        time.sleep(1.5)
    except Exception as e:
        print(f"Error starting {script}: {e}")

print("\n" + "=" * 60)
print("Saari scripts start ho gayi hain!")
print("Band karne ke liye Ctrl + C dabao")
print("=" * 60)

try:
    for name, p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nStopping all scripts...")
    for name, p in processes:
        p.terminate()
        print(f"Stopped: {name}")