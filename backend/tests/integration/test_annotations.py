#!/usr/bin/env python3
"""
Tests for photo annotation API endpoints.

Covers:
- POST /api/annotations/photos/{photo_id} (create)
- GET /api/annotations/photos/{photo_id} (list)
- PUT /api/annotations/{id} (update / supersede)
- DELETE /api/annotations/{id} (tombstone delete)
- POST /api/annotations/{id}/hide (moderator soft tombstone)
- Hidden user filtering in annotation listing
- Supersede chain conflict detection (409)
"""

import requests
import os
import sys

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseUserManagementTest
from utils.test_utils import API_URL, clear_test_database


def own_public_photo_id(token):
    """Id of a public photo the calling user just uploaded.

    Deliberately not the first hit of a world-bbox /hillview query: the dev
    database is shared and usually holds hundreds of other people's photos, so
    that query hands back a stranger's photo and the tests below then annotate
    a photo they do not own. The owner listing can only return your own.
    """
    resp = requests.get(
        f"{API_URL}/photos/",
        params={"only_processed": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Photo listing failed: {resp.status_code}: {resp.text}"
    mine = [p for p in resp.json()["photos"] if p["is_public"]]
    assert mine, "No photos after create_test_photos — check worker"
    return mine[0]["id"]


class TestAnnotationCRUD(BaseUserManagementTest):
    """Test basic annotation CRUD operations."""

    def setup_method(self, method=None):
        super().setup_method(method)
        # Upload test photos so we have a photo_id to annotate
        self.create_test_photos(self.test_users, self.auth_tokens)
        self.photo_id = own_public_photo_id(self.test_token)

    def test_create_annotation(self):
        """Test creating a new annotation."""
        response = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={
                "body": "Test annotation",
                "target": {
                    "selector": {
                        "type": "RECTANGLE",
                        "geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
                    }
                },
            },
            headers=self.test_headers,
        )
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["body"] == "Test annotation"
        assert data["is_current"] is True
        assert data["event_type"] == "created"
        assert data["photo_id"] == self.photo_id

    def test_create_annotation_on_nonexistent_photo(self):
        """Creating annotation on missing photo returns 404."""
        response = requests.post(
            f"{API_URL}/annotations/photos/nonexistent-id",
            json={"body": "Orphan annotation"},
            headers=self.test_headers,
        )
        assert response.status_code == 404

    def test_create_annotation_unauthenticated(self):
        """Creating annotation without auth returns 401."""
        response = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "No auth"},
        )
        assert response.status_code in (401, 403)

    def test_list_annotations(self):
        """Test listing annotations for a photo."""
        # Create an annotation first
        requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Listing test"},
            headers=self.test_headers,
        )

        # List (unauthenticated — should still work)
        response = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        bodies = [a["body"] for a in data]
        assert "Listing test" in bodies

    def test_update_annotation_supersedes(self):
        """Updating an annotation creates a new version and supersedes the old one."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Original"},
            headers=self.test_headers,
        )
        assert create_resp.status_code == 201
        original_id = create_resp.json()["id"]

        update_resp = requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Updated"},
            headers=self.test_headers,
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["body"] == "Updated"
        assert updated["event_type"] == "updated"
        assert updated["is_current"] is True
        assert updated["id"] != original_id

    def test_update_already_superseded_returns_409(self):
        """Updating a non-current annotation returns 409."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Will be superseded"},
            headers=self.test_headers,
        )
        original_id = create_resp.json()["id"]

        requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Superseded version"},
            headers=self.test_headers,
        )

        response = requests.put(
            f"{API_URL}/annotations/{original_id}",
            json={"body": "Should fail"},
            headers=self.test_headers,
        )
        assert response.status_code == 409

    def test_delete_annotation_creates_tombstone(self):
        """Deleting an annotation creates a tombstone and hides it from listings."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "To be deleted"},
            headers=self.test_headers,
        )
        ann_id = create_resp.json()["id"]

        delete_resp = requests.delete(
            f"{API_URL}/annotations/{ann_id}",
            headers=self.test_headers,
        )
        assert delete_resp.status_code == 204

        list_resp = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        assert list_resp.status_code == 200
        bodies = [a["body"] for a in list_resp.json()]
        assert "To be deleted" not in bodies

    def test_delete_already_superseded_returns_409(self):
        """Deleting a non-current annotation returns 409."""
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Will be superseded then deleted"},
            headers=self.test_headers,
        )
        ann_id = create_resp.json()["id"]

        requests.put(
            f"{API_URL}/annotations/{ann_id}",
            json={"body": "New version"},
            headers=self.test_headers,
        )

        response = requests.delete(
            f"{API_URL}/annotations/{ann_id}",
            headers=self.test_headers,
        )
        assert response.status_code == 409

    def test_delete_nonexistent_returns_404(self):
        """Deleting a nonexistent annotation returns 404."""
        response = requests.delete(
            f"{API_URL}/annotations/nonexistent-uuid",
            headers=self.test_headers,
        )
        assert response.status_code == 404


class TestAnnotationHide(BaseUserManagementTest):
    """Moderator hide: a 'hidden' event that removes the annotation from
    listings and counts while keeping body/target in the chain tip (so the
    enrichment workbench still sees a normal current annotation)."""

    def setup_method(self, method=None):
        # This class asserts on the bestof ranking, which is global and shows
        # 20 rows: any photo left in the database by another test or another
        # branch would decide whether ours makes the page. Wipe first, then let
        # the base setup recreate the users the wipe just deleted.
        clear_test_database()
        super().setup_method(method)
        self.create_test_photos(self.test_users, self.auth_tokens)
        self.photo_id = own_public_photo_id(self.test_token)

    def _create(self, body, headers=None):
        resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={
                "body": body,
                "target": {
                    "selector": {
                        "type": "RECTANGLE",
                        "geometry": {"bounds": {"minX": 10, "minY": 20, "maxX": 30, "maxY": 40}},
                    }
                },
            },
            headers=headers or self.test_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        return resp.json()

    def _list_bodies(self):
        resp = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        assert resp.status_code == 200
        return [a["body"] for a in resp.json()]

    def test_hide_requires_moderator(self):
        """Ordinary users cannot hide annotations."""
        ann = self._create("Regular user cannot hide this")
        resp = requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.test_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"

    def test_hide_annotation(self):
        """Hiding appends a 'hidden' tip carrying body/target and drops the
        annotation from the public listing."""
        ann = self._create("Hill duplicated by terrain overlay")
        assert "Hill duplicated by terrain overlay" in self._list_bodies()

        resp = requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        hidden = resp.json()
        assert hidden["event_type"] == "hidden"
        assert hidden["is_current"] is True
        assert hidden["id"] != ann["id"]
        # Soft tombstone: body/target carried forward for the workbench
        assert hidden["body"] == ann["body"]
        assert hidden["target"] == ann["target"]

        assert "Hill duplicated by terrain overlay" not in self._list_bodies()

    def test_hide_guards(self):
        """404 for missing/deleted chains, 409 for superseded or already-hidden rows."""
        # Superseded (non-current) row → 409
        ann = self._create("Guard: will be superseded")
        requests.put(
            f"{API_URL}/annotations/{ann['id']}",
            json={"body": "Guard: new version"},
            headers=self.test_headers,
        )
        resp = requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        )
        assert resp.status_code == 409

        # Already-hidden tip → 409
        ann2 = self._create("Guard: hide twice")
        hidden = requests.post(
            f"{API_URL}/annotations/{ann2['id']}/hide",
            headers=self.admin_headers,
        ).json()
        resp = requests.post(
            f"{API_URL}/annotations/{hidden['id']}/hide",
            headers=self.admin_headers,
        )
        assert resp.status_code == 409

        # Nonexistent → 404
        resp = requests.post(
            f"{API_URL}/annotations/nonexistent-uuid/hide",
            headers=self.admin_headers,
        )
        assert resp.status_code == 404

    def test_hidden_excluded_from_effective_count(self):
        """Hidden annotations drop out of the shared effective-count subquery
        (exercised via the bestof endpoint's counts and bodies)."""
        body = "Bestof visibility probe annotation"
        # A second annotation keeps the photo scoring after the hide, so the
        # post-hide assertions below are about the count and not about the
        # photo falling off the listing entirely.
        keeper = "Bestof annotation that stays visible"
        ann = self._create(body)
        self._create(keeper)

        def bestof_photo():
            """Our photo's row in the ranking, or None if it stopped scoring.

            Page one is the whole ranking here — setup wiped the database, so
            the only photo that scores at all is the one we just annotated.
            """
            resp = requests.get(f"{API_URL}/bestof/photos")
            assert resp.status_code == 200
            for p in resp.json()["photos"]:
                if p["id"] == self.photo_id:
                    return p
            return None

        before = bestof_photo()
        assert before is not None, "Annotated photo should appear in bestof"
        assert body in before["annotations"]
        assert keeper in before["annotations"]
        count_before = before["annotation_count"]

        requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        )

        after = bestof_photo()
        assert after is not None, "Photo still scores through the second annotation"
        assert body not in after["annotations"]
        assert keeper in after["annotations"]
        assert after["annotation_count"] == count_before - 1

    def test_undo_hide_restores(self):
        """Undoing the hide event resurfaces the annotation as an 'updated' tip."""
        body = "Unhide me later"
        ann = self._create(body)
        hidden = requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        ).json()
        assert body not in self._list_bodies()

        resp = requests.post(
            f"{API_URL}/admin/annotation-events/{hidden['id']}/undo",
            json={},
            headers=self.admin_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["action"] == "undo_hide"

        listing = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}").json()
        restored = [a for a in listing if a["body"] == body]
        assert restored, "Annotation should be visible again after undo"
        assert restored[0]["event_type"] == "updated"

    def test_contributions_standing_after_hide(self):
        """A moderator hide is dedup housekeeping: the author's chain still
        counts as standing (mine_is_current looks through the hide event)."""
        body = "Standing survives a hide"
        ann = self._create(body)
        requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        )

        resp = requests.get(
            f"{API_URL}/annotations/contributions",
            headers=self.test_headers,
        )
        assert resp.status_code == 200
        items = [c for c in resp.json()["contributions"] if c["current_body"] == body]
        assert items, "Hidden chain should still appear in contributions"
        assert items[0]["status"] == "live"
        assert items[0]["mine_is_current"] is True

    def test_update_resurfaces_hidden(self):
        """A user PUT on the hidden tip appends an 'updated' event, which
        resurfaces the chain (tip rule) — documented semantics."""
        ann = self._create("Hidden then edited")
        hidden = requests.post(
            f"{API_URL}/annotations/{ann['id']}/hide",
            headers=self.admin_headers,
        ).json()

        resp = requests.put(
            f"{API_URL}/annotations/{hidden['id']}",
            json={"body": "Edited back to visibility"},
            headers=self.test_headers,
        )
        assert resp.status_code == 200
        assert "Edited back to visibility" in self._list_bodies()


class TestAnnotationHiddenUserFiltering(BaseUserManagementTest):
    """Test that hidden user annotations are filtered from listings."""

    def setup_method(self, method=None):
        super().setup_method(method)
        self.create_test_photos(self.test_users, self.auth_tokens)
        self.photo_id = own_public_photo_id(self.test_token)

    def test_hidden_user_annotations_filtered(self):
        """Annotations by hidden users should not appear in listing."""
        # Admin creates an annotation
        create_resp = requests.post(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            json={"body": "Admin annotation for filtering test"},
            headers=self.admin_headers,
        )
        assert create_resp.status_code == 201
        admin_ann = create_resp.json()
        admin_user_id = admin_ann["user_id"]

        # Visible in unauthenticated listing
        list_resp = requests.get(f"{API_URL}/annotations/photos/{self.photo_id}")
        bodies = [a["body"] for a in list_resp.json()]
        assert "Admin annotation for filtering test" in bodies

        # Test user hides the admin user
        hide_resp = requests.post(
            f"{API_URL}/hidden/users",
            json={
                "target_user_source": "hillview",
                "target_user_id": admin_user_id,
                "reason": "Test filtering",
            },
            headers=self.test_headers,
        )
        assert hide_resp.status_code == 200, f"Failed to hide user: {hide_resp.text}"

        # Now list as the test user — admin's annotation should be filtered out
        list_resp = requests.get(
            f"{API_URL}/annotations/photos/{self.photo_id}",
            headers=self.test_headers,
        )
        assert list_resp.status_code == 200
        bodies = [a["body"] for a in list_resp.json()]
        assert "Admin annotation for filtering test" not in bodies, \
            f"Hidden user's annotation should not appear. Got bodies: {bodies}"

        # Cleanup: unhide the admin user
        requests.delete(
            f"{API_URL}/hidden/users",
            json={
                "target_user_source": "hillview",
                "target_user_id": admin_user_id,
            },
            headers=self.test_headers,
        )
