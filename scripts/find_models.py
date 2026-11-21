import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "3DModelBot/1.0 (personal reference search, low volume)"
MAX_CARDS = 5
TIMEOUT_S = 30
PRINTABLES_API = "https://api.printables.com/graphql/"
PRINTABLES_MEDIA = "https://media.printables.com/"
SI_API = "https://3d-api.si.edu/api/v1.0/content/file/search"
THINGIVERSE_API = "https://api.thingiverse.com"
SI_DOWNLOAD_ORDER = (("Download3D", "Low_Resolution"), ("Download3D", "Full_Resolution"), ("Web3D", "High"), ("Web3D", "Medium"))
PRINTABLES_SEARCH = """query ($q: String!, $limit: Int) { searchPrints2(query: $q, limit: $limit) { items {
  id name slug premium price image { filePath } user { publicUsername handle }
  license { name abbreviation } stls { id name fileSize } } } }"""
PRINTABLES_LINK = """mutation ($id: ID!, $printId: ID!) { getDownloadLink(id: $id, printId: $printId, fileType: stl, source: model_detail) {
  ok errors { field messages } output { link } } }"""


def http_json(url, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.load(response)


class DropAuthOnHostChange(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            new.remove_header("Authorization")
        return new


def http_file(url, path, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    opener = urllib.request.build_opener(DropAuthOnHostChange)
    with opener.open(request, timeout=TIMEOUT_S * 4) as response, open(path, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    return path


def can_sell(license_name):
    text = (license_name or "").lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    if not text:
        return "no"
    if "cc0" in words or "public domain" in text:
        return "yes"
    if words & {"noncommercial", "nc"} or "non-commercial" in text or "standard digital" in text:
        return "no"
    if words & {"noderivatives", "noderivs", "nd"} or "no derivatives" in text:
        return "no"
    if words & {"attribution", "by", "gpl", "lgpl", "bsd", "mit"}:
        return "attribution-required"
    return "no"


def search_printables(query, limit):
    items = http_json(PRINTABLES_API, {"query": PRINTABLES_SEARCH, "variables": {"q": query, "limit": limit}})["data"]["searchPrints2"]["items"]
    cards = []
    for item in items:
        if item.get("premium") or item.get("price"):
            continue
        license_name = (item.get("license") or {}).get("name", "")
        cards.append({
            "id": f"printables:{item['id']}",
            "name": item["name"],
            "link": f"https://www.printables.com/model/{item['id']}-{item['slug']}",
            "thumbnail": PRINTABLES_MEDIA + item["image"]["filePath"] if item.get("image") else None,
            "author": (item.get("user") or {}).get("publicUsername"),
            "license": license_name,
            "can_sell": can_sell(license_name),
            "source": "Printables",
            "files": [{"id": s["id"], "name": s["name"]} for s in item.get("stls") or []],
        })
    return cards


def search_smithsonian(query, limit):
    rows = http_json(f"{SI_API}?{urllib.parse.urlencode({'q': query, 'rows': 60})}")["rows"]
    packages = {}
    for row in rows:
        content = row["content"]
        package = packages.setdefault(content["model_url"], {"title": re.sub(r"<[^>]+>", "", row["title"]), "files": []})
        package["files"].append({"usage": content.get("usage"), "quality": content.get("quality"), "type": content.get("file_type"), "url": content["uri"]})
    cards = []
    for package_id, package in list(packages.items())[:limit]:
        thumb = next((f["url"] for f in package["files"] if f["quality"] == "Thumb"), None)
        cards.append({
            "id": f"si:{package_id}",
            "name": package["title"],
            "link": f"https://3d-api.si.edu/voyager/{package_id}",
            "thumbnail": thumb,
            "author": "Smithsonian Institution",
            "license": "CC0 (Smithsonian Open Access)",
            "can_sell": "yes",
            "source": "Smithsonian 3D",
            "files": package["files"],
        })
    return cards


def thingiverse_headers():
    return {"Authorization": f"Bearer {os.environ['THINGIVERSE_TOKEN']}"}


def search_thingiverse(query, limit):
    term = urllib.parse.quote(query)
    hits = http_json(f"{THINGIVERSE_API}/search/{term}?type=things&per_page={limit}", headers=thingiverse_headers()).get("hits", [])
    cards = []
    for hit in hits[:limit]:
        license_name = http_json(f"{THINGIVERSE_API}/things/{hit['id']}", headers=thingiverse_headers()).get("license", "")
        cards.append({
            "id": f"thingiverse:{hit['id']}",
            "name": hit["name"],
            "link": hit.get("public_url"),
            "thumbnail": hit.get("thumbnail"),
            "author": (hit.get("creator") or {}).get("name"),
            "license": license_name,
            "can_sell": can_sell(license_name),
            "source": "Thingiverse",
            "files": [],
        })
    return cards


def interleave(groups, limit):
    cards = []
    while len(cards) < limit and any(groups):
        for group in groups:
            if group and len(cards) < limit:
                cards.append(group.pop(0))
    return cards


def manual_links(query):
    q = urllib.parse.quote(query)
    return {
        "MakerWorld": f"https://makerworld.com/en/search/models?keyword={q}",
        "Thangs": f"https://thangs.com/search/{q}?scope=all",
    }


def to_markdown(query, cards, notes, links):
    lines = [f"Reference results for \"{query}\" (nothing has been downloaded yet):", ""]
    for i, card in enumerate(cards, 1):
        lines.append(f"{i}. [{card['name']}]({card['link']}) · {card['source']} · author {card['author']} · {card['license']} · can sell: {card['can_sell']} · id `{card['id']}`")
        if card["thumbnail"]:
            lines.append(f"   preview: {card['thumbnail']}")
    lines += ["", "Open these yourself (the bot does not fetch them automatically): " + " · ".join(f"[{k}]({v})" for k, v in links.items())]
    lines += [f"Note: {n}" for n in notes]
    return "\n".join(lines)


def cmd_search(args):
    sources = [("Smithsonian 3D", search_smithsonian), ("Printables", search_printables)]
    notes = []
    if os.environ.get("THINGIVERSE_TOKEN"):
        sources.append(("Thingiverse", search_thingiverse))
    else:
        notes.append("Skipping Thingiverse: THINGIVERSE_TOKEN is not set.")
    groups = []
    for name, fn in sources:
        try:
            found = fn(args.query, MAX_CARDS)
        except (OSError, KeyError, ValueError) as err:
            notes.append(f"{name} failed: {type(err).__name__}")
            found = []
        if not found:
            notes.append(f"{name}: no results.")
        groups.append(found)
    cards = interleave(groups, MAX_CARDS)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"query": args.query, "cards": cards, "manual_links": manual_links(args.query), "notes": notes}
    (out / "search_cache.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cards"} | {"cards": [{k: v for k, v in c.items() if k != "files"} for c in cards]}, ensure_ascii=False, indent=2))
    print()
    print(to_markdown(args.query, cards, notes, result["manual_links"]))
    return 0 if cards else 1


def download_printables(card, folder):
    model_id = card["id"].split(":", 1)[1]
    if not card["files"]:
        raise SystemExit("This Printables model has no public STL file.")
    first = card["files"][0]
    result = http_json(PRINTABLES_API, {"query": PRINTABLES_LINK, "variables": {"id": first["id"], "printId": model_id}})["data"]["getDownloadLink"]
    if not result["ok"]:
        raise SystemExit(f"Printables refused the download link: {result['errors']}")
    return [http_file(result["output"]["link"], folder / Path(first["name"]).name)]


def download_smithsonian(card, folder):
    for usage, quality in SI_DOWNLOAD_ORDER:
        match = next((f for f in card["files"] if f["usage"] == usage and f["quality"] == quality), None)
        if match:
            return [http_file(match["url"], folder / Path(urllib.parse.urlparse(match["url"]).path).name)]
    raise SystemExit("No downloadable file was found in this Smithsonian package.")


def download_thingiverse(card, folder):
    if not os.environ.get("THINGIVERSE_TOKEN"):
        raise SystemExit("THINGIVERSE_TOKEN is required to download from Thingiverse.")
    thing_id = card["id"].split(":", 1)[1]
    files = http_json(f"{THINGIVERSE_API}/things/{thing_id}/files", headers=thingiverse_headers())
    stls = [f for f in files if f["name"].lower().endswith((".stl", ".3mf", ".obj"))]
    if not stls:
        raise SystemExit("This Thingiverse model has no STL/3MF/OBJ file.")
    return [http_file(stls[0]["download_url"], folder / Path(stls[0]["name"]).name, thingiverse_headers())]


def mesh_problem(path):
    if path.suffix.lower() not in (".stl", ".3mf", ".obj", ".glb", ".gltf", ".ply"):
        return f"{path.name}: not a mesh that can be read directly (it may be compressed); decompress or inspect it."
    try:
        import trimesh
        mesh = trimesh.load(path, force="mesh")
    except Exception as err:
        return f"{path.name}: trimesh could not read the file ({type(err).__name__})."
    if len(mesh.faces) == 0 or float(mesh.extents.max()) == 0.0:
        return f"{path.name}: the mesh is empty or all coordinates are 0 (often caused by Draco compression). Pick another model, or open it in Blender and export an STL."
    return None


DOWNLOADERS = {"printables": download_printables, "si": download_smithsonian, "thingiverse": download_thingiverse}


def cmd_download(args):
    out = Path(args.out)
    cache = json.loads((out / "search_cache.json").read_text(encoding="utf-8"))
    card = next((c for c in cache["cards"] if c["id"] == args.id), None)
    if card is None:
        raise SystemExit(f"Id {args.id} was not in the latest search. Run the search command again.")
    if args.commercial and card["can_sell"] not in ("yes", "attribution-required"):
        raise SystemExit(f"Refused: the license \"{card['license']}\" does not allow commercial use or does not allow derivatives.")
    folder = out / re.sub(r"[^A-Za-z0-9_.-]+", "_", card["id"])
    folder.mkdir(parents=True, exist_ok=True)
    files = DOWNLOADERS[card["id"].split(":", 1)[0]](card, folder)
    sidecar = {k: card[k] for k in ("id", "name", "link", "author", "license", "can_sell", "source")}
    sidecar |= {"files": [str(f) for f in files], "commercial_use_requested": args.commercial}
    warnings = [w for w in (mesh_problem(Path(f)) for f in files) if w]
    if len(card["files"]) > 1 and card["id"].startswith("printables:"):
        warnings.append(f"The model has {len(card['files'])} STL files; only the first one was downloaded.")
    if warnings:
        sidecar["canh_bao"] = warnings
    (folder / "license.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(sidecar, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Search reference 3D models (Smithsonian, Printables, Thingiverse) and download the one the owner picks.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--out", default="out/models")
    p = sub.add_parser("download")
    p.add_argument("id", help="card id, for example printables:743015")
    p.add_argument("--out", default="out/models")
    p.add_argument("--commercial", action="store_true", help="intended for sale of prints or remixes: reject NC, ND, and unknown licenses")
    args = parser.parse_args(argv)
    return cmd_search(args) if args.cmd == "search" else cmd_download(args)


if __name__ == "__main__":
    sys.exit(main())
