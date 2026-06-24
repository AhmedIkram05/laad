"""Configuration for continuous log generator."""

import os
from dotenv import load_dotenv

load_dotenv()

# Generator tuning
TICK_SECONDS = int(os.getenv("TICK_SECONDS", "1"))
BACKFILL_MINUTES = int(os.getenv("BACKFILL_MINUTES", "60"))
ANOMALY_PROB = float(os.getenv("ANOMALY_PROB", "0.002"))
GENERATOR_SEED = os.getenv("GENERATOR_SEED", "")
BACKFILL_MODE = os.getenv("BACKFILL_MODE", "false").lower() in (
    "true",
    "1",
    "yes",
)  # "" = true random

# Fleet configuration
ATMS = [f"ATM-GB-{str(i).zfill(4)}" for i in range(1, 11)]
SERVERS = [f"ATM-SERVER-{str(i).zfill(3)}" for i in range(1, 4)]
ALL_ENTITIES = ATMS + SERVERS
ATM_LOCATIONS = {atm: f"LOC-{str(i).zfill(3)}" for i, atm in enumerate(ATMS, 1)}
POD_NAME = "terminal-handler-pod-0"
OS_VERSION = "Windows-Server-2019"
