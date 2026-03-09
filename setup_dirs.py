import os

dirs = [
    "engine/config",
    "engine/data",
    "engine/data/images",
    "engine/state",
    "engine/library",
    "engine/queue",
    "engine/modules",
    "engine/output",
    "engine/output/yt",
    "engine/output/tt",
    "engine/output/fb",
    "engine/config/tokens",
    "engine/assets"
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    print(f"Created/Verified directory: {d}")
