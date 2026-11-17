import sys
from pathlib import Path

ETL = Path(__file__).resolve().parents[1]
ROOT = ETL.parent
sys.path.insert(0, str(ETL))
