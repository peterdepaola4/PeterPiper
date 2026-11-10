"""
Put the project's GitHub address (and, later, its Zenodo DOI) everywhere it
belongs, in one step - run it once after making the GitHub repository:

    python build/set_github.py https://github.com/<account>/PeterPiper
    python build/set_github.py https://github.com/<account>/PeterPiper --doi 10.5281/zenodo.1234567

It updates (only these, and only the marked places):
    app/peterpiper/__init__.py   PROJECT_URL, PROJECT_DOI   (Help > About PeterPiper)
    CITATION.cff             repository-code, url, doi   (GitHub's 'Cite this repository')
    README.md                the citation in section 11.5 and the download line at the top
    READ ME.txt              the 'Project page' line
then rebuild the manual (python build/md2html.py README.md README.html) and commit.
Running it again with another address replaces the old one.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER = "https://github.com/<your-account>/PeterPiper"


def _rw(rel: str, fn) -> bool:
    p = REPO / rel
    s = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in s
    new = fn(s.replace("\r\n", "\n"))
    if crlf:
        new = new.replace("\n", "\r\n")
    if new.encode("utf-8") != p.read_bytes():
        p.write_bytes(new.encode("utf-8"))
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url", help="the repository address, e.g. https://github.com/me/PeterPiper")
    ap.add_argument("--doi", default="", help="the Zenodo DOI, e.g. 10.5281/zenodo.1234567")
    a = ap.parse_args(argv)
    url = a.url.strip().rstrip("/")
    if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", url):
        print(f"Not a GitHub repository address: {url}")
        return 2
    doi = a.doi.strip()
    if doi and not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        print(f"Not a DOI: {doi}")
        return 2
    changed = []

    def init(s):
        s = re.sub(r'^PROJECT_URL = ".*"$', f'PROJECT_URL = "{url}"', s, flags=re.M)
        if doi:
            s = re.sub(r'^PROJECT_DOI = ".*"$', f'PROJECT_DOI = "{doi}"', s, flags=re.M)
        return s
    if _rw("app/peterpiper/__init__.py", init):
        changed.append("app/peterpiper/__init__.py")

    def cff(s):
        s = re.sub(r"^(repository-code|url|doi):.*\n", "", s, flags=re.M)
        extra = f'repository-code: "{url}"\nurl: "{url}"\n' + (f'doi: "{doi}"\n' if doi else "")
        return s.replace("license: MIT\n", "license: MIT\n" + extra, 1)
    if _rw("CITATION.cff", cff):
        changed.append("CITATION.cff")

    def readme(s):
        s = re.sub(r"https://github\.com/(<your-account>|[\w.-]+)/PeterPiper(?=[ \].)\n/])", url, s)
        if doi:                                 # only PeterPiper's own citation line
            out = []
            for line in s.split("\n"):
                if "DePaola P IV. PeterPiper" in line:
                    line = re.sub(r"\[add the Zenodo DOI once archived\]|"
                                  r"https://doi\.org/10\.\S+?(?=[\s)\]]|\.?$)",
                                  f"https://doi.org/{doi}", line)
                out.append(line)
            s = "\n".join(out)
        return s
    if _rw("README.md", readme):
        changed.append("README.md")

    def readme_txt(s):
        return re.sub(r"^Project page: .*$", f"Project page: {url}", s, flags=re.M)
    if _rw("READ ME.txt", readme_txt):
        changed.append("READ ME.txt")
    print("updated: " + (", ".join(changed) if changed else "nothing (already set)"))
    print("next: python build/md2html.py README.md README.html, then commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
