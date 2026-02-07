# app/services/handicap_rfeg.py
import re
import requests
from bs4 import BeautifulSoup

RFEG_URL = "https://rfegolf.es/PaginasServicios/ServicioHandicap.aspx?HLic={lic}"

def _norm_license(s: str | None) -> str:
    return re.sub(r"\s+", "", (s or "")).upper()

def _parse_float_es(s: str) -> float:
    # "20,2" -> 20.2  /  "20.2" -> 20.2
    s = (s or "").strip().replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        raise ValueError(f"No se pudo parsear handicap desde: {s!r}")
    return float(m.group(0))

def fetch_rfeg_handicap(license_number: str, timeout: int = 12) -> dict:
    lic = _norm_license(license_number)
    if not lic:
        raise ValueError("Licencia vacía")

    url = RFEG_URL.format(lic=lic)
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "GolfMode/1.0"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    def norm_hdr(x: str) -> str:
        return (x or "").strip().lower().replace("á", "a").replace("í", "i").replace("é", "e").replace("ó", "o").replace("ú", "u")

    # Recorre todas las tablas y busca la que tenga una cabecera de resultados
    for table in soup.find_all("table"):
        header_tr = table.find("tr")
        if not header_tr:
            continue

        headers = [norm_hdr(th.get_text(" ", strip=True)) for th in header_tr.find_all(["th", "td"])]
        if not headers:
            continue

        # Comprobamos que parece la tabla correcta
        if "licencia" not in " ".join(headers) or "handicap" not in " ".join(headers):
            continue

        # Mapeo de índices por nombre de columna
        def find_idx(keyword: str) -> int | None:
            for i, h in enumerate(headers):
                if keyword in h:
                    return i
            return None

        idx_lic = find_idx("licencia")
        idx_hcp = find_idx("handicap")  # "handicap" o "handicap" sin tilde ya
        idx_mod = find_idx("mod")       # "modificacion" suele contener "mod"

        if idx_lic is None or idx_hcp is None:
            continue

        # Recorremos filas (saltamos cabecera)
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all(["td", "th"])
            cols = [td.get_text(" ", strip=True) for td in tds]
            if len(cols) <= max(idx_lic, idx_hcp):
                continue

            lic_col = _norm_license(cols[idx_lic])
            if lic_col != lic:
                continue

            hcp_val = _parse_float_es(cols[idx_hcp])
            last_mod = cols[idx_mod] if (idx_mod is not None and idx_mod < len(cols)) else None

            return {
                "license": lic,
                "handicap": hcp_val,
                "last_modified": last_mod,
                "raw_cols": cols,
                "source_url": url,
            }

    # Si no encontró nada, lo decimos claro
    raise LookupError(f"No se encontró la licencia {lic} en el resultado (o cambió la estructura).")
