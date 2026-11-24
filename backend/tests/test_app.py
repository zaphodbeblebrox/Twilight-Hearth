import io
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from authlib.integrations.starlette_client import OAuthError
from PIL import Image as PILImage
from sqlalchemy import select

from app.config import Settings
from app.ingredients import parse
from app.models import Invite, now
from app.security import create_invite

from .conftest import content, dev_login, make_recipe, new_client


def token(db, **kwargs):
    return create_invite(db, **kwargs)[1].split("#")[1]


# Login and invites


def test_uninvited_is_refused(db):
    response = dev_login(new_client(), "ann")
    assert response.status_code == 403
    assert response.json()["detail"] == "invite_required"


def test_invite_works_once_and_returning_users_need_none(db):
    invite = token(db)
    assert dev_login(new_client(), "ann", invite).status_code == 204
    assert dev_login(new_client(), "ann").status_code == 204
    assert dev_login(new_client(), "bob", invite).json()["detail"] == "invite_invalid"


def test_email_invite_only_fits_that_email(db):
    invite = token(db, email="Ann@Example.com")
    assert dev_login(new_client(), "bob", invite).json()["detail"] == "invite_email_mismatch"
    assert dev_login(new_client(), "ann", invite).status_code == 204


@pytest.mark.parametrize("field", ["expires_at", "revoked_at"])
def test_expired_or_revoked_invite(db, field):
    invite = token(db)
    setattr(db.scalar(select(Invite)), field, now() - timedelta(minutes=1))
    db.commit()
    assert dev_login(new_client(), "ann", invite).json()["detail"] == "invite_invalid"


def google(client, claims=None, error=None):
    fake = Mock(
        authorize_access_token=AsyncMock(return_value={"userinfo": claims}, side_effect=error)
    )
    with patch("app.routers.auth.google_client", return_value=fake):
        return client.get("/api/auth/google/callback", follow_redirects=False)


def test_google_callback(db):
    claims = {"sub": "1", "email": "ann@example.com", "email_verified": False, "name": "Ann"}
    client = new_client()
    assert google(client, claims).headers["location"].endswith("error=invite_required")
    assert google(client, error=OAuthError()).headers["location"].endswith("google_failed")
    client.post("/api/auth/invite", json={"token": token(db, email="ann@example.com")})
    assert google(client, claims).headers["location"].endswith("invite_email_mismatch")
    response = google(client, claims | {"email_verified": True})
    assert response.headers["location"] == "http://testserver/"
    assert client.get("/api/auth/me").json()["email"] == "ann@example.com"
    # Identity follows Google's id even when the email changes.
    assert google(new_client(), claims | {"email": "new@example.com"}).status_code == 303
    assert client.get("/api/auth/me").json()["email"] == "new@example.com"


def test_production_refuses_unsafe_settings(monkeypatch):
    for name in ("TH_ENV", "TH_PUBLIC_URL", "TH_GOOGLE_CLIENT_ID"):
        monkeypatch.delenv(name)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(_env_file=None)


def test_logout_and_disable_end_sessions(join):
    admin, bob = join("ann", admin=True), join("bob")
    assert bob.get("/api/admin/users").status_code == 403
    bob_id = bob.get("/api/auth/me").json()["id"]
    assert admin.post(f"/api/admin/users/{bob_id}/disable").status_code == 204
    assert bob.get("/api/auth/me").status_code == 401
    assert dev_login(bob, "bob").json()["detail"] == "account_disabled"
    admin.post("/api/auth/logout")
    assert admin.get("/api/auth/me").status_code == 401


def test_everything_needs_login_and_same_origin(join):
    recipe = make_recipe(join("ann"))
    for path in ("recipes", "tags", f"recipes/{recipe['id']}", "admin/users"):
        assert new_client().get(f"/api/{path}").status_code == 401
    ann = join("cat")
    response = ann.post(
        "/api/recipes", json={"content": content()}, headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403


# Recipes and history


def test_edit_history_and_restore(join):
    ann = join("ann")
    recipe = make_recipe(ann)
    url = f"/api/recipes/{recipe['id']}"
    for number in (1, 2):
        body = {"content": content(f"Edit {number}"), "base_number": number}
        assert ann.put(url, json=body).status_code == 200
    stale = ann.put(url, json={"content": content("Stale"), "base_number": 1})
    assert stale.status_code == 409
    restored = ann.post(f"{url}/restore", json={"number": 1, "base_number": 3}).json()
    assert (restored["title"], restored["current_number"]) == ("Pancakes", 4)
    assert [r["number"] for r in ann.get(f"{url}/revisions").json()] == [4, 3, 2, 1]
    assert ann.get(f"{url}/revisions/2").json()["content"]["title"] == "Edit 1"


def test_only_owner_changes_recipe(join):
    ann, bob = join("ann"), join("bob")
    url = f"/api/recipes/{make_recipe(ann)['id']}"
    assert bob.put(url, json={"content": content(), "base_number": 1}).status_code == 403
    assert bob.delete(url).status_code == 403
    assert bob.put(f"{url}/visibility", json={"visibility": "private"}).status_code == 403
    assert bob.post(f"{url}/restore", json={"number": 1, "base_number": 1}).status_code == 403


def test_private_recipe_is_hidden_everywhere(join):
    ann, bob = join("ann"), join("bob")
    recipe = make_recipe(ann, "Secret", "private", tags=["hush"])
    url = f"/api/recipes/{recipe['id']}"
    for path in ("", "/revisions", "/revisions/1", "/forks", "/comments"):
        assert ann.get(url + path).status_code == 200
        assert bob.get(url + path).status_code == 404
    assert bob.post(f"{url}/fork").status_code == 404
    assert bob.put(f"{url}/favorite").status_code == 404
    assert bob.put(f"{url}/rating", json={"stars": 5}).status_code == 404
    assert bob.get("/api/recipes?q=secret").json()["total"] == 0
    assert bob.get("/api/tags").json() == []
    assert ann.get("/api/tags").json() == [{"tag": "hush", "count": 1}]


def test_search_filter_and_sort(join):
    ann = join("ann")
    make_recipe(ann, "Pancakes", tags=["Breakfast"], cook_minutes=10)
    make_recipe(ann, "Stew", tags=["dinner"], cook_minutes=5)

    def titles(query):
        return [r["title"] for r in ann.get(f"/api/recipes?{query}").json()["items"]]

    assert titles("q=pancake") == ["Pancakes"]
    assert titles("q=flour&sort=title") == ["Pancakes", "Stew"]
    assert titles("q=%25") == []
    assert titles("tag=breakfast") == ["Pancakes"]
    assert titles("sort=quick") == ["Stew", "Pancakes"]


# Forks


def test_fork_is_an_independent_copy_that_cites_its_source(join):
    ann, bob, cat = join("ann"), join("bob"), join("cat")
    original = make_recipe(ann)
    url = f"/api/recipes/{original['id']}"
    ann.put(url, json={"content": content("Better pancakes"), "base_number": 1})
    fork = bob.post(f"{url}/fork").json()
    assert fork["can_edit"] and fork["title"] == "Better pancakes"
    source = fork["sources"][0]
    assert (source["recipe_id"], source["number"]) == (original["id"], 2)
    assert source["owner"]["display_name"] == "Ann"

    fork_url = f"/api/recipes/{fork['id']}"
    body = {"content": content("Bob's pancakes"), "base_number": 1}
    edited = bob.put(fork_url, json=body).json()
    assert edited["sources"] == fork["sources"]
    assert ann.get(url).json()["title"] == "Better pancakes"
    assert [f["title"] for f in ann.get(f"{url}/forks").json()] == ["Bob's pancakes"]

    second = cat.post(f"{fork_url}/fork").json()
    assert [s["owner"]["display_name"] for s in second["sources"]] == ["Bob", "Ann"]


@pytest.mark.parametrize("hide", ["private", "delete"])
def test_hidden_source_keeps_credit_but_reveals_nothing(join, hide):
    ann, bob = join("ann"), join("bob")
    url = f"/api/recipes/{make_recipe(ann)['id']}"
    fork = bob.post(f"{url}/fork").json()
    if hide == "delete":
        ann.delete(url)
    else:
        ann.put(f"{url}/visibility", json={"visibility": "private"})
    source = bob.get(f"/api/recipes/{fork['id']}").json()["sources"][0]
    assert source["owner"]["display_name"] == "Ann"
    assert source["available"] is False
    assert source["recipe_id"] is source["title"] is source["number"] is None


def test_fork_of_private_recipe_starts_private(join):
    ann = join("ann")
    recipe = make_recipe(ann, visibility="private")
    assert ann.post(f"/api/recipes/{recipe['id']}/fork").json()["visibility"] == "private"


# Social


def test_favorites_ratings_and_comments(join):
    ann, bob, cat = join("ann"), join("bob"), join("cat")
    url = f"/api/recipes/{make_recipe(ann)['id']}"
    for _ in range(2):
        assert bob.put(f"{url}/favorite").status_code == 204
    assert bob.get("/api/recipes?favorites=true").json()["total"] == 1
    assert ann.get("/api/recipes?favorites=true").json()["total"] == 0
    bob.put(f"{url}/rating", json={"stars": 1})
    bob.put(f"{url}/rating", json={"stars": 5})
    cat.put(f"{url}/rating", json={"stars": 4})
    seen = bob.get(url).json()
    assert (seen["rating"], seen["rating_count"], seen["my_rating"]) == (4.5, 2, 5)
    comment = bob.post(f"{url}/comments", json={"body": "Yum"}).json()
    assert cat.delete(f"{url}/comments/{comment['id']}").status_code == 403
    assert bob.delete(f"{url}/comments/{comment['id']}").status_code == 204


# Images


def picture():
    image = PILImage.new("RGB", (3000, 1000), "red")
    exif = PILImage.Exif()
    exif[0x010E] = "private location"
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_images_are_cleaned_and_follow_recipe_visibility(join):
    ann, bob = join("ann"), join("bob")
    image_id = ann.post("/api/images", files={"file": ("a.jpg", picture())}).json()["id"]
    url = f"/api/images/{image_id}"
    shown = PILImage.open(io.BytesIO(ann.get(url).content))
    assert shown.format == "WEBP" and max(shown.size) == 1600 and not shown.getexif()

    recipe = make_recipe(ann, visibility="private", image_id=image_id)
    assert bob.get(url).status_code == 404
    # Naming someone's hidden image must not expose it.
    stolen = bob.post("/api/recipes", json={"content": content(image_id=image_id)})
    assert stolen.status_code == 422
    ann.put(f"/api/recipes/{recipe['id']}/visibility", json={"visibility": "members"})
    assert bob.get(url).status_code == 200
    # A fork keeps its picture after the original is deleted.
    bob.post(f"/api/recipes/{recipe['id']}/fork")
    ann.delete(f"/api/recipes/{recipe['id']}")
    assert bob.get(url).status_code == 200


def test_bad_uploads_are_refused(join):
    ann = join("ann")
    for data in (b"not an image", b"<svg xmlns='http://www.w3.org/2000/svg'/>"):
        assert ann.post("/api/images", files={"file": ("a.jpg", data)}).status_code == 422


# Validation


def test_content_validation(join):
    ann = join("ann")
    duplicate = [{"id": "s1", "text": "a"}, {"id": "s1", "text": "b"}]
    for bad in (
        {"title": "  "},
        {"source_url": "javascript:alert(1)"},
        {"steps": duplicate},
        {"servings": 0},
    ):
        response = ann.post("/api/recipes", json={"content": content() | bad})
        assert response.status_code == 422, bad
    assert make_recipe(ann, "Nul\x00 soup")["title"] == "Nul soup"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 1/2 cups flour", ("3/2", None, "cup", "flour")),
        ("1½ cups flour", ("3/2", None, "cup", "flour")),
        ("½ tsp. salt", ("1/2", None, "teaspoon", "salt")),
        ("2-3 cloves of garlic", ("2", "3", "clove", "garlic")),
        ("1 to 2 T oil", ("1", "2", "tablespoon", "oil")),
        ("0.5 kg beef", ("1/2", None, "kilogram", "beef")),
        ("3 eggs", ("3", None, None, "eggs")),
        ("salt to taste", (None, None, None, "salt to taste")),
        ("2% milk", (None, None, None, "2% milk")),
        ("2-inch piece ginger", (None, None, None, "2-inch piece ginger")),
        ("1/0 cup x", (None, None, None, "1/0 cup x")),
    ],
)
def test_ingredient_parsing(text, expected):
    assert tuple(parse(text).values()) == expected
