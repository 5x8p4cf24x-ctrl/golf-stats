from pathlib import Path
from datetime import datetime
import shutil

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "golf_stats.db"
BACKUP_DIR = BASE_DIR / "backups"

# Crear carpeta si no existe
BACKUP_DIR.mkdir(exist_ok=True)

# Nombre del backup con fecha y hora
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
backup_file = BACKUP_DIR / f"golf_stats_{timestamp}.db"

# Copiar DB
if DB_FILE.exists():
    shutil.copy(DB_FILE, backup_file)
    print(f"✅ Backup creado: {backup_file.name}")
else:
    print("❌ No se encontró la base de datos")
