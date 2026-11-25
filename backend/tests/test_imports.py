import io
import json
import threading
import zipfile
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image as PILImage
from pypdf import PdfWriter
from sqlalchemy import select

from app import fetch as fetching
from app import importer
from app.config import get_settings
from app.models import ImportJob, Recipe
from app.routers import imports

from .conftest import new_client

SCHEMA = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Mum&#39;s <b>Soup</b>",
    "author": {"@type": "Person", "name": "Ann"},
    "image": "/soup.png",
    "recipeYield": "4 servings",
    "prepTime": "PT10M",
    "cookTime": "PT1H",
    "recipeCategory": "Dinner",
    "recipeIngredient": ["1 1/2 cups stock", "salt (, to taste)"],
    "recipeInstructions": [
        {"@type": "HowToStep", "text": "Chop."},
        {"@type": "HowToStep", "text": "Boil at 100&deg;."},
    ],
}
PAGE = f'<!doctype html><html><script type="application/ld+json">{json.dumps(SCHEMA)}</script>'
DRAFT = {
    "found": True,
    "title": "Card",
    "description": "",
    "servings": -1,
    "yield_note": "",
    "prep_minutes": None,
    "cook_minutes": 5,
    "ingredient_groups": [{"name": "", "items": ["2 eggs", " "]}],
    "steps": ["Fry.", "x" * 6000],
    "notes": "",
    "tags": ["Breakfast"],
    "source_name": "Gran",
}


def png() -> bytes:
    out = io.BytesIO()
    PILImage.new("RGB", (40, 30), "red").save(out, "PNG")
    return out.getvalue()


def pdf(pages: int) -> bytes:
    writer, out = PdfWriter(), io.BytesIO()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    writer.write(out)
    return out.getvalue()


def docx(xml: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


def send(client, data: bytes, name="recipe"):
    return client.post("/api/imports/file", files={"file": (name, data)})


@pytest.fixture
def model(monkeypatch):
    """A fake model: set .answers to what each call returns; .calls records requests."""
    fake = SimpleNamespace(answers=[], calls=[])

    class Client:
        def __init__(self, **_):
            self.messages = self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create(self, **request):
            fake.calls.append(request)
            answer = fake.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return SimpleNamespace(
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=1000, output_tokens=1000),
                content=[SimpleNamespace(type="text", text=json.dumps(answer))],
            )

    monkeypatch.setattr(importer.anthropic, "Anthropic", Client)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test")
    return fake


@pytest.fixture
def site(monkeypatch):
    """A local web site that the importer is allowed to reach. Set .pages by path."""
    site = SimpleNamespace(pages={})

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            page = site.pages.get(self.path)
            self.send_response(302 if isinstance(page, str) else 200 if page else 404)
            if isinstance(page, str):
                self.send_header("Location", page)
            self.end_headers()
            if isinstance(page, bytes):
                self.wfile.write(page)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(fetching, "PORTS", {server.server_port})
    monkeypatch.setattr(fetching, "is_public", lambda address: address == "127.0.0.1")
    site.url = f"http://127.0.0.1:{server.server_port}"
    yield site
    server.shutdown()
    server.server_close()


def test_url_import_fills_a_draft_and_saves_no_recipe(join, db, site):
    site.pages = {"/go": "/r", "/r": PAGE.encode(), "/soup.png": png()}
    ann = join("ann")
    response = ann.post("/api/imports/url", json={"url": f"{site.url}/go"})
    assert response.status_code == 200, response.text
    draft = response.json()["content"]
    assert draft["title"] == "Mum's Soup"
    assert draft["servings"] == 4 and draft["yield_note"] == ""
    assert (draft["prep_minutes"], draft["cook_minutes"]) == (10, 60)
    assert [i["text"] for i in draft["ingredient_groups"][0]["items"]] == [
        "1 1/2 cups stock",
        "salt (to taste)",
    ]
    assert [s["text"] for s in draft["steps"]] == ["Chop.", "Boil at 100°."]
    assert draft["tags"] == ["dinner"] and "Ann" in draft["source_name"]
    assert draft["source_url"] == f"{site.url}/r"
    assert ann.get(f"/api/images/{draft['image_id']}").status_code == 200
    assert db.scalar(select(Recipe)) is None
    # What comes back can be saved as it is.
    assert ann.post("/api/recipes", json={"content": draft}).status_code == 201
    job = db.scalar(select(ImportJob))
    assert not job.used_model and job.cost == 0


def test_missing_picture_does_not_stop_an_import(join, site):
    site.pages = {"/r": PAGE.encode()}
    response = join("ann").post("/api/imports/url", json={"url": f"{site.url}/r"})
    assert response.status_code == 200
    assert response.json()["content"]["image_id"] is None


def test_page_without_recipe_data_uses_the_model(join, site, model):
    page = b"<html><script>secret()</script><nav>Menu</nav><p>Two eggs, fry.</p></html>"
    site.pages = {"/r": page}
    model.answers = [DRAFT]
    response = join("ann").post("/api/imports/url", json={"url": f"{site.url}/r"})
    assert response.json()["content"]["title"] == "Card"
    assert model.calls[0]["messages"][0]["content"] == [{"type": "text", "text": "Two eggs, fry."}]


def test_private_addresses_are_refused(join, site, monkeypatch):
    monkeypatch.undo()
    for url in (
        site.url,
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]/",
        "http://10.0.0.1",
        "http://169.254.169.254/latest",
        "http://[::ffff:127.0.0.1]/",
        "http://0x7f000001/",
    ):
        with pytest.raises(HTTPException, match="Could not open"):
            fetching.fetch(url, max_bytes=100, seconds=3)
    # Even when the port is right, the address is what decides.
    monkeypatch.setattr(fetching, "PORTS", {int(site.url.split(":")[-1])})
    site.pages = {"/": b"private"}
    with pytest.raises(HTTPException, match="Could not open"):
        fetching.fetch(site.url, max_bytes=100, seconds=3)


def test_redirect_to_private_address_is_refused(site):
    for target in ("http://10.0.0.1/", "file:///etc/passwd", "http://127.0.0.1:8100/"):
        site.pages = {"/": target}
        with pytest.raises(HTTPException, match="Could not open"):
            fetching.fetch(site.url, max_bytes=100, seconds=3)


@pytest.mark.parametrize(
    "address,expected",
    [
        ("8.8.8.8", True),
        ("2606:4700::1", True),
        ("100.64.0.1", False),
        ("224.0.0.1", False),
        ("0.0.0.0", False),
        ("fe80::1%eth0", False),
        ("fd00::1", False),
        ("64:ff9b::7f00:1", False),
        ("2002:7f00:1::", False),
    ],
)
def test_public_addresses(address, expected):
    assert fetching.is_public(address) is expected


def test_large_and_missing_pages(site):
    site.pages = {"/big": b"x" * 200}
    for path, message in (("/big", "too large"), ("/none", "error 404")):
        with pytest.raises(HTTPException, match=message):
            fetching.fetch(site.url + path, max_bytes=100, seconds=3)


def test_bad_addresses(join):
    ann = join("ann")
    for url in ("ftp://example.com", "https://", "javascript://x", "https://u:p@example.com", " "):
        assert ann.post("/api/imports/url", json={"url": url}).status_code == 422
    assert fetching.check_url("example.com/a") == "https://example.com/a"


def test_schema_files_need_no_model(join):
    ann = join("ann")
    for data in (PAGE.encode(), json.dumps(SCHEMA).encode(), json.dumps([SCHEMA]).encode()):
        response = send(ann, data)
        assert response.status_code == 200, response.text
        assert response.json()["content"]["title"] == "Mum's Soup"
        assert response.json()["content"]["source_url"] == ""


def test_photo_is_cleaned_and_read(join, db, model):
    model.answers = [DRAFT]
    response = send(join("ann"), png(), "card.png")
    assert response.status_code == 200, response.text
    draft = response.json()["content"]
    assert draft["title"] == "Card" and draft["servings"] is None
    assert len(draft["ingredient_groups"][0]["items"]) == 1
    assert [len(s["text"]) for s in draft["steps"]] == [4, 5000, 1000]
    request = model.calls[0]
    assert request["model"] == get_settings().import_model
    assert request["messages"][0]["content"][0]["source"]["media_type"] == "image/webp"
    job = db.scalar(select(ImportJob))
    assert job.used_model and job.cost == Decimal("0.0006")


def test_documents_are_read(join, model):
    ann = join("ann")
    word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = f'<w:d xmlns:w="{word}"><w:p><w:t>2 eggs</w:t></w:p><w:p><w:t>Fry</w:t></w:p></w:d>'
    model.answers = [DRAFT] * 3
    assert send(ann, docx(xml)).status_code == 200
    assert send(ann, b"2 eggs").status_code == 200
    assert send(ann, pdf(2)).status_code == 200
    sent = [call["messages"][0]["content"][0] for call in model.calls]
    assert [s.get("text") for s in sent] == ["2 eggs\nFry", "2 eggs", None]
    assert sent[2]["source"]["media_type"] == "application/pdf"


def test_bad_files_are_refused_without_calling_the_model(join, model, monkeypatch):
    ann = join("ann")
    bomb = '<!DOCTYPE x [<!ENTITY a "a">]><x>&a;</x>'
    for data in (
        b"",
        b"  ",
        b"a\x00b",
        b"%PDF-nope",
        b"PK\x03\x04no",
        docx(bomb),
        pdf(11),
        b"\x89PNG",
    ):
        assert send(ann, data).status_code == 422, data[:20]
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 10)
    assert send(ann, b"x" * 11).status_code == 413
    assert not model.calls


def test_second_model_is_tried(join, db, model):
    ann = join("ann")
    model.answers = [{**DRAFT, "found": False}, DRAFT]
    assert send(ann, png()).status_code == 200
    assert [c["model"] for c in model.calls] == [
        get_settings().import_model,
        get_settings().import_retry_model,
    ]
    assert db.scalar(select(ImportJob)).cost == Decimal("0.0126")


def test_failures_are_explained_and_charged(join, db, model):
    ann = join("ann")
    model.answers = [{**DRAFT, "found": False}] * 2
    assert "No recipe" in send(ann, png()).json()["detail"]
    model.answers = [importer.anthropic.APIConnectionError(request=None), {"wrong": 1}]
    assert send(ann, png()).status_code == 502
    model.answers = [importer.anthropic.APITimeoutError(request=None)] * 2
    assert send(ann, png()).status_code == 502
    costs = sorted(db.scalars(select(ImportJob.cost)))
    assert costs == [Decimal("0.012"), Decimal("0.0126"), Decimal("0.126")]


def test_partial_recipe_data_is_kept_when_the_model_is_unavailable(join):
    part = {k: v for k, v in SCHEMA.items() if k != "recipeInstructions"}
    response = send(join("ann"), json.dumps(part).encode())
    assert response.status_code == 200
    assert "part of the recipe" in response.json()["notice"]


def test_without_a_key_photos_are_explained(join):
    response = send(join("ann"), png())
    assert response.status_code == 503 and "not set up" in response.json()["detail"]


def test_limits(join, db, model, monkeypatch):
    settings = get_settings()
    ann, bob = join("ann"), join("bob")
    model.answers = [DRAFT] * 5
    monkeypatch.setattr(settings, "import_daily_model_limit", 1)
    assert send(ann, png()).status_code == 200
    assert send(ann, png()).status_code == 429
    # Each member has their own limit, and pages with recipe data are not affected.
    assert send(bob, png()).status_code == 200
    assert send(ann, PAGE.encode()).status_code == 200
    monkeypatch.setattr(settings, "import_daily_limit", 3)
    assert send(ann, PAGE.encode()).status_code == 429

    monkeypatch.setattr(settings, "import_daily_model_limit", 20)
    monkeypatch.setattr(settings, "import_monthly_dollars", 0.5)
    response = send(bob, png())
    assert response.status_code == 429 and "budget" in response.json()["detail"]


def test_imports_need_login_and_a_free_slot(join):
    assert send(new_client(), PAGE.encode()).status_code == 401
    assert new_client().post("/api/imports/url", json={"url": "x.com"}).status_code == 401
    ann = join("ann")
    for _ in range(4):
        imports.slots.acquire()
    try:
        assert send(ann, PAGE.encode()).status_code == 503
    finally:
        for _ in range(4):
            imports.slots.release()
    assert send(ann, PAGE.encode()).status_code == 200
