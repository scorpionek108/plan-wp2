#!/usr/bin/env python3
"""Pobiera aktualny PDF z planem zajęć (Wzornictwo przemysłowe, rok 2) ze strony WM PL.

Nazwy plików na stronie: wp1_<rok>_rok_zima_26-27[-1|_vN].pdf, a sam link zawiera
długi token, więc plik rozpoznajemy po nazwie (wp1_2_rok_...), a zmianę po hashu treści.
Skrypt wypisuje szczegóły (kod HTTP, rozmiar odpowiedzi), żeby w logu Actions było widać,
co dokładnie poszło nie tak.
"""
import datetime
import hashlib
import pathlib
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE = "https://wm.pollub.pl/studenci/plany-zajec"
PATTERN = re.compile(r"/wp1_2_rok_[^/?#]*\.pdf(?:$|[?#])", re.I)  # wp1 = wzornictwo, 2 = rok 2
RAW = re.compile(r"[^\s\"'<>()]*wp1_2_rok_[^\s\"'<>()]*\.pdf", re.I)
HEADERS = {  # niektóre serwery blokują domyślny „python-requests”
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
}
DATA = pathlib.Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)


def get(url, tries=3):
    """GET z ponawianiem przy błędach sieci i kodach 429/5xx."""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=45)
            if r.status_code != 429 and r.status_code < 500:
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        print(f"  próba {i + 1}/{tries} nieudana: {last}")
        if i < tries - 1:
            time.sleep(5 * (i + 1))
    sys.exit(f"Nie udało się pobrać {url[:80]} ({last})")


def find_pdf_url() -> str:
    r = get(PAGE)
    print(f"Strona wydziału: HTTP {r.status_code}, {len(r.text)} znaków, adres końcowy: {r.url}")
    if r.status_code != 200:
        print("Początek odpowiedzi:", r.text[:300].replace("\n", " "))
        sys.exit(f"Strona wydziału zwróciła HTTP {r.status_code} (blokada lub awaria po stronie serwera?)")
    soup = BeautifulSoup(r.text, "html.parser")
    hrefs = [a["href"] for a in soup.find_all("a", href=True)]
    urls = [urljoin(r.url, h) for h in hrefs if PATTERN.search(h)]
    if not urls:  # awaryjnie: adres w dowolnym miejscu kodu strony (np. w skryptach)
        urls = [urljoin(r.url, u.replace("\\/", "/")) for u in RAW.findall(r.text)]
    if not urls:
        pdfs = [h for h in hrefs if ".pdf" in h.lower()]
        print(f"Na stronie jest {len(hrefs)} linków, w tym {len(pdfs)} do PDF-ów:")
        for h in pdfs[:12]:
            print("  ", h[-70:])
        print("Początek odpowiedzi:", r.text[:300].replace("\n", " "))
        sys.exit("Nie znaleziono linku do planu (zmieniła się nazwa pliku lub strona?)")
    # gdy na stronie są plany zimowy i letni, wybierz bieżący semestr
    season = "lato" if 2 <= datetime.date.today().month <= 6 else "zima"
    for u in urls:
        if season in u.lower():
            return u
    return urls[0]


def main() -> int:
    url = find_pdf_url()
    print("Wybrany plik:", url.rsplit("/", 1)[-1])
    r = get(url)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        print("Typ odpowiedzi:", r.headers.get("Content-Type"), "| początek:", r.content[:120])
        sys.exit(f"Pobranie PDF-a nie powiodło się (HTTP {r.status_code}, to nie jest plik PDF)")
    pdf = r.content
    digest = hashlib.sha256(pdf).hexdigest()
    hash_file = DATA / "plan.sha256"
    if hash_file.exists() and hash_file.read_text().strip() == digest:
        print("Bez zmian.")
        return 0
    (DATA / "plan.pdf").write_bytes(pdf)
    print("Nowa wersja planu, rozmiar:", len(pdf), "B")
    import parse_plan
    parse_plan.main(DATA / "plan.pdf", DATA / "plan.json")  # przy błędzie hash się nie zapisze
    hash_file.write_text(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
