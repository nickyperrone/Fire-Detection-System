from app.services.tags import PALETTE


def rect(west):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, -33.0],
                [west + 0.01, -33.0],
                [west + 0.01, -32.99],
                [west, -32.99],
                [west, -33.0],
            ]
        ],
    }


def test_tags_get_distinct_colors_once_and_keep_them(client):
    client.post(
        "/territories",
        json={"name": "A", "geometry": rect(-59.10), "tags": ["crop:soy", "cliente 1", "casa"]},
    )
    first = client.get("/tags").json()
    assert first["palette"] == list(PALETTE)
    # Plain labels first, then key:value tags.
    assert [t["label"] for t in first["tags"]] == ["casa", "cliente 1", "crop:soy"]
    colors = [t["color"] for t in first["tags"]]
    assert len(set(colors)) == 3 and set(colors) <= set(PALETTE)
    assert client.get("/tags").json() == first


def test_a_tag_color_can_be_changed_only_to_a_palette_color(client):
    client.post("/territories", json={"name": "A", "geometry": rect(-59.10), "tags": ["casa"]})
    casa = client.get("/tags").json()["tags"][0]
    changed = client.patch(f"/tags/{casa['id']}", json={"color": PALETTE[-1]}).json()
    assert changed["color"] == PALETTE[-1]
    red = client.patch(f"/tags/{casa['id']}", json={"color": "#ef4444"})
    assert (red.status_code, red.json()["code"]) == (422, "unknown_color")
    assert client.patch("/tags/999", json={"color": PALETTE[0]}).json()["code"] == "tag_not_found"
