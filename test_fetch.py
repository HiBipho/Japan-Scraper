import requests
import sys

# Gunakan header yang sama dengan scraper utama
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
}

# Ambil URL dari argumen baris perintah
url = sys.argv[1]

print(f"[*] Mengambil data dari: {url}")

try:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    # Simpan konten HTML mentah ke file
    with open("output.html", "w", encoding="utf-8") as f:
        f.write(response.text)

    print("[+] Konten berhasil disimpan ke output.html")
    print(f"[*] Kode Status: {response.status_code}")

except requests.exceptions.RequestException as e:
    print(f"[!] Gagal mengambil data: {e}")
