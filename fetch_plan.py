#!/usr/bin/env python3
"""Pobiera aktualny PDF z planem zajęć (Wzornictwo przemysłowe, rok 2) ze strony WM PL.

Nazwy plików na stronie: wp1_<rok>_rok_zima_26-27[-1|_vN].pdf, a sam link zawiera
długi token, więc plik rozpoznajemy po nazwie (wp1_2_rok_...), a zmianę po hashu treści.
"""
import datetime
import hashlib
import pathlib
import re
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE = "https://wm.pollub.pl/studenci/plany-zajec"
PATTERN = re.compile(r"/wp1_2_rok_[^/]*\.pdf$", re.I)  # wp1 = wzornictwo, 2 = rok 2
DATA = pathlib.Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)


def find_pdf_url() -> str:
    html = requests.get(PAGE, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    urls = [urljoin(PAGE, a["href"]) for a in soup.find_all("a", href=True)
            if PATTERN.search(a["href"])]
    if not urls:
        sys.exit("Nie znaleziono linku do planu (zmieniła się nazwa pliku lub strona?)")
    # gdy na stronie są plany zimowy i letni, wybierz bieżący semestr
    season = "lato" if 2 <= datetime.date.today().month <= 6 else "zima"
    for u in urls:
        if season in u.lower():
            return u
    return urls[0]


def main() -> int:
    url = find_pdf_url()
    pdf = requests.get(url, timeout=60).content
    digest = hashlib.sha256(pdf).hexdigest()
    hash_file = DATA / "plan.sha256"
    if hash_file.exists() and hash_file.read_text().strip() == digest:
        print("Bez zmian.")
        return 0
    (DATA / "plan.pdf").write_bytes(pdf)
    print("Nowa wersja planu:", url.rsplit("/", 1)[-1])
    import parse_plan
    parse_plan.main(DATA / "plan.pdf", DATA / "plan.json")  # przy błędzie hash się nie zapisze
    hash_file.write_text(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
