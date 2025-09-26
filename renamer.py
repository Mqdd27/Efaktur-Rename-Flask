# renamer.py
import io
import os
import re
from typing import Optional, Tuple, List, Tuple as Tup
from PyPDF2 import PdfReader

# --- Regex utama ---
# (Referensi: ... ) → ambil isi di dalamnya (longgar)
RE_REF = re.compile(r"\(?\s*Referensi:?\s*(?P<ref>[^)\n\r]+?)\s*\)?", re.IGNORECASE)

# Nomor seri faktur pajak setelah frasa ini (boleh ada titik/dash/spasi) → lalu dinormalisasi jadi digit saja
RE_SERI = re.compile(
    r"Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak\s*:\s*(?P<seri>[\d\.\-\s]+)",
    re.IGNORECASE,
)

# Format ketat nomor invoice yang kamu pakai: INV/2025/09/0654
RE_INV_STRICT = re.compile(r"\bINV/\d{4}/\d{2}/\d{4}\b", re.IGNORECASE)


def _sanitize(s: str) -> str:
    """Bersihkan bagian nama file dari karakter ilegal & rapikan spasi."""
    s = s.strip()
    s = re.sub(r"[\\/:\*\?\"<>\|\r\n\t]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_for_search(s: str) -> str:
    """
    Normalisasi teks hasil ekstraksi PDF:
    - Gabungkan whitespace berturut-turut jadi satu spasi.
    - Hilangkan spasi/newline di sekitar slash agar 'INV / 2025 / 09 / 0654' -> 'INV/2025/09/0654'.
    """
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*/\s*", "/", s)
    return s


def _invoice_ref_to_filename(ref: str, allow_unicode_slash: bool = True) -> str:
    # ganti '/' ASCII -> FULLWIDTH SLASH '／' (U+FF0F) agar "terlihat" slash tapi aman di Windows
    return ref.replace("/", "／") if allow_unicode_slash else ref.replace("/", "-")

def parse_pdf_fields(file_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Ekstrak (ref invoice, nomor seri faktur) dari PDF.
    Return: (ref, seri) keduanya sudah disanitasi (tanpa '/' untuk ref, seri berisi digit saja).
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        chunks = []
        for p in reader.pages:
            chunks.append(p.extract_text() or "")
        raw = "\n".join(chunks)
    except Exception:
        return None, None

    # Normalisasi untuk meningkatkan keberhasilan regex
    norm = _normalize_for_search(raw)

    # 1) Cari nomor seri faktur pajak
    seri = None
    m_seri = RE_SERI.search(norm)
    if m_seri:
        seri = m_seri.group("seri")
        # sisakan digit/dot/dash lalu normalisasi jadi digit saja
        seri = re.sub(r"[^\d\.\-]", "", seri)
        seri = seri.replace(".", "").replace("-", "")
        seri = _sanitize(seri)

    # 2) Cari nomor invoice
    ref = None
    # 2a) Utamakan pola ketat INV/YYYY/MM/NNNN
    m_inv = RE_INV_STRICT.search(norm)
    if m_inv:
        ref = m_inv.group(0).upper()
    else:
        # 2b) fallback dari "(Referensi: ...)" → jika di dalamnya ada INV/.. ambil itu
        m_ref = RE_REF.search(norm)
        if m_ref:
            candidate = _sanitize(m_ref.group("ref"))
            inner = RE_INV_STRICT.search(candidate)
            ref = (inner.group(0).upper() if inner else candidate)

    if ref:
        ref = _invoice_ref_to_filename(_sanitize(ref))  # "INV-2025-09-0654"

    return (ref or None), (seri or None)


def build_new_name(ref: Optional[str], seri: Optional[str], pretty_slash: bool = True) -> Optional[str]:
    if not ref or not seri:
        return None
    ref_disp = _invoice_ref_to_filename(_sanitize(ref), allow_unicode_slash=pretty_slash)
    base = _sanitize(f"{ref_disp} - {seri}")
    return f"{base}.pdf" if base else None

def process_files(file_storages, dry_run: bool = False):
    """
    Input: list of FileStorage (request.files.getlist('file'))
    Return:
      - results: List[str] log hasil
      - outputs: List[Tuple[str, bytes]] pasangan (nama_baru, isi_pdf) bila sukses
    """
    results: List[str] = []
    outputs: List[Tup[str, bytes]] = []

    for fs in file_storages:
        fname = fs.filename or ""
        if not fname.lower().endswith(".pdf"):
            results.append(f"❌ Bukan PDF: {fname}")
            continue

        data = fs.read()
        if not data:
            results.append(f"❌ File kosong: {fname}")
            continue

        ref, seri = parse_pdf_fields(data)
        new_name = build_new_name(ref, seri, pretty_slash=True)

        if new_name:
            # Hindari duplikat nama di batch
            existing = {n for n, _ in outputs}
            final = new_name
            i = 1
            while final in existing:
                stem, _ext = os.path.splitext(new_name)
                final = f"{stem} ({i}).pdf"
                i += 1

            results.append(f"✅ {fname} → {final}")
            if not dry_run:
                outputs.append((final, data))
        else:
            if not ref and not seri:
                results.append(f"⚠️ {fname}: Referensi & Nomor Seri tidak ditemukan.")
            elif not ref:
                results.append(f"⚠️ {fname}: Referensi tidak ditemukan.")
            else:
                results.append(f"⚠️ {fname}: Nomor Seri Faktur Pajak tidak ditemukan.")

    return results, outputs
