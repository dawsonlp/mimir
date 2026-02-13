"""
Integration tests for Phase 2 Deletion Infrastructure.

All tests exercise the Mimir REST API via httpx (no mocks, no direct SQL).
Requires: docker compose up (API on port 38000, PostgreSQL on 35432)
          Migration 006 applied

Run: cd backend && .venv/bin/python -m pytest tests/integration/test_deletion_phase2.py -v -s
"""

from uuid import uuid4

import pytest


# =============================================================================
# Helpers
# =============================================================================


async def _create_tenant(client, tenant_type="environment"):
    """Create a tenant via API and return the response dict."""
    shortname = f"del-{tenant_type[:3]}-{uuid4().hex[:6]}"
    resp = await client.post(
        "/tenants",
        json={"shortname": shortname, "name": f"Deletion Test {tenant_type}", "tenant_type": tenant_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_artifact(client, tenant_id, title="Test", parent_id=None, artifact_type="document"):
    """Create an artifact via API and return the response dict."""
    body = {"artifact_type": artifact_type, "title": title, "content": f"Content of {title}"}
    if parent_id:
        body["parent_artifact_id"] = str(parent_id)
    resp = await client.post(
        "/artifacts",
        headers={"X-Tenant-ID": str(tenant_id)},
        json=body,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_relation(client, tenant_id, source_id, target_id, relation_type="references"):
    """Create a relation via API and return the response dict."""
    resp = await client.post(
        "/relations",
        headers={"X-Tenant-ID": str(tenant_id)},
        json={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation_type": relation_type,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# =============================================================================
# Tenant Deletion Policy
# =============================================================================


@pytest.mark.integration
class TestTenantDeletionPolicy:
    """Verify deletion_policy is exposed on tenant responses."""

    @pytest.mark.asyncio
    async def test_environment_tenant_has_soft_delete_policy(self, async_client):
        """Environment tenant response includes deletion_policy = soft_delete."""
        tenant = await _create_tenant(async_client, "environment")
        resp = await async_client.get(f"/tenants/{tenant['id']}")
        assert resp.status_code == 200
        assert resp.json()["deletion_policy"] == "soft_delete"

    @pytest.mark.asyncio
    async def test_project_tenant_has_no_delete_policy(self, async_client):
        """Project tenant response includes deletion_policy = no_delete."""
        tenant = await _create_tenant(async_client, "project")
        resp = await async_client.get(f"/tenants/{tenant['id']}")
        assert resp.status_code == 200
        assert resp.json()["deletion_policy"] == "no_delete"

    @pytest.mark.asyncio
    async def test_experiment_tenant_has_physical_delete_policy(self, async_client):
        """Experiment tenant response includes deletion_policy = physical_delete."""
        tenant = await _create_tenant(async_client, "experiment")
        resp = await async_client.get(f"/tenants/{tenant['id']}")
        assert resp.status_code == 200
        assert resp.json()["deletion_policy"] == "physical_delete"


# =============================================================================
# Soft Delete — Environment Tenant
# =============================================================================


@pytest.mark.integration
class TestSoftDelete:
    """Soft-delete via DELETE /artifacts/{id} with environment tenant."""

    @pytest.fixture
    async def env_tenant(self, async_client):
        return await _create_tenant(async_client, "environment")

    @pytest.mark.asyncio
    async def test_soft_delete_returns_soft_delete_response(self, async_client, env_tenant):
        """DELETE returns SoftDeleteResponse with deleted_id, cascade_count, deleted_at."""
        art = await _create_artifact(async_client, env_tenant["id"], title="SoftDel Single")
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        resp = await async_client.delete(f"/artifacts/{art['id']}", headers=headers)
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["deleted_id"] == art["id"]
        assert body["cascade_count"] == 0
        assert body["deleted_at"] is not None
        assert art["id"] in body["deleted_ids"]

    @pytest.mark.asyncio
    async def test_soft_deleted_artifact_returns_404(self, async_client, env_tenant):
        """GET /artifacts/{id} returns 404 for soft-deleted artifact."""
        art = await _create_artifact(async_client, env_tenant["id"], title="Gone")
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)

        resp = await async_client.get(f"/artifacts/{art['id']}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_deleted_visible_with_include_deleted(self, async_client, env_tenant):
        """GET /artifacts/{id}?include_deleted=true returns soft-deleted artifact."""
        art = await _create_artifact(async_client, env_tenant["id"], title="StillVisible")
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)

        resp = await async_client.get(
            f"/artifacts/{art['id']}", headers=headers, params={"include_deleted": "true"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_at"] is not None

    @pytest.mark.asyncio
    async def test_delete_already_deleted_returns_404(self, async_client, env_tenant):
        """DELETE on an already-deleted artifact returns 404."""
        art = await _create_artifact(async_client, env_tenant["id"], title="DeleteTwice")
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)
        resp = await async_client.delete(f"/artifacts/{art['id']}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, async_client, env_tenant):
        """DELETE on a nonexistent artifact returns 404."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}
        fake_id = str(uuid4())

        resp = await async_client.delete(f"/artifacts/{fake_id}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded_from_list(self, async_client, env_tenant):
        """Soft-deleted artifacts are excluded from GET /artifacts list."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}
        art = await _create_artifact(async_client, env_tenant["id"], title="ListExclude")

        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)

        resp = await async_client.get("/artifacts", headers=headers)
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()["items"]]
        assert art["id"] not in ids


# =============================================================================
# Cascade Soft Delete
# =============================================================================


@pytest.mark.integration
class TestCascadeSoftDelete:
    """Cascade soft-delete via parent_artifact_id tree."""

    @pytest.fixture
    async def env_tenant(self, async_client):
        return await _create_tenant(async_client, "environment")

    @pytest.mark.asyncio
    async def test_cascade_deletes_all_descendants(self, async_client, env_tenant):
        """DELETE with cascade=true soft-deletes parent + all descendants."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        parent = await _create_artifact(async_client, env_tenant["id"], title="Parent")
        child1 = await _create_artifact(async_client, env_tenant["id"], title="Child1", parent_id=parent["id"])
        child2 = await _create_artifact(async_client, env_tenant["id"], title="Child2", parent_id=parent["id"])
        grandchild = await _create_artifact(async_client, env_tenant["id"], title="Grandchild", parent_id=child1["id"])

        resp = await async_client.delete(
            f"/artifacts/{parent['id']}", headers=headers, params={"cascade": "true"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cascade_count"] == 3  # child1, child2, grandchild
        assert len(body["deleted_ids"]) == 4

        # All should return 404
        for art_id in [parent["id"], child1["id"], child2["id"], grandchild["id"]]:
            get_resp = await async_client.get(f"/artifacts/{art_id}", headers=headers)
            assert get_resp.status_code == 404, f"Artifact {art_id} should be 404 after cascade delete"

    @pytest.mark.asyncio
    async def test_cascade_does_not_affect_unrelated(self, async_client, env_tenant):
        """Cascade delete only affects descendants, not unrelated artifacts."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        unrelated = await _create_artifact(async_client, env_tenant["id"], title="Unrelated")
        parent = await _create_artifact(async_client, env_tenant["id"], title="CParent")
        child = await _create_artifact(async_client, env_tenant["id"], title="CChild", parent_id=parent["id"])

        await async_client.delete(f"/artifacts/{parent['id']}", headers=headers, params={"cascade": "true"})

        # Unrelated should still be accessible
        resp = await async_client.get(f"/artifacts/{unrelated['id']}", headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_cascade_with_children_returns_409(self, async_client, env_tenant):
        """DELETE with cascade=false when children exist returns 409."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        parent = await _create_artifact(async_client, env_tenant["id"], title="NoCascParent")
        await _create_artifact(async_client, env_tenant["id"], title="NoCascChild", parent_id=parent["id"])

        resp = await async_client.delete(
            f"/artifacts/{parent['id']}", headers=headers, params={"cascade": "false"}
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_no_cascade_leaf_succeeds(self, async_client, env_tenant):
        """DELETE with cascade=false on a leaf artifact succeeds."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}
        leaf = await _create_artifact(async_client, env_tenant["id"], title="Leaf")

        resp = await async_client.delete(
            f"/artifacts/{leaf['id']}", headers=headers, params={"cascade": "false"}
        )
        assert resp.status_code == 200


# =============================================================================
# Policy Enforcement — no_delete (Project Tenant)
# =============================================================================


@pytest.mark.integration
class TestNoDeletePolicy:
    """Project tenants with no_delete policy get 403 on DELETE."""

    @pytest.fixture
    async def proj_tenant(self, async_client):
        return await _create_tenant(async_client, "project")

    @pytest.mark.asyncio
    async def test_delete_returns_403_for_project_tenant(self, async_client, proj_tenant):
        """DELETE /artifacts/{id} returns 403 for project (no_delete) tenant."""
        art = await _create_artifact(async_client, proj_tenant["id"], title="Undeletable")
        headers = {"X-Tenant-ID": str(proj_tenant["id"])}

        resp = await async_client.delete(f"/artifacts/{art['id']}", headers=headers)
        assert resp.status_code == 403

        # Artifact should still be accessible
        get_resp = await async_client.get(f"/artifacts/{art['id']}", headers=headers)
        assert get_resp.status_code == 200


# =============================================================================
# Physical Delete — Experiment Tenant
# =============================================================================


@pytest.mark.integration
class TestPhysicalDelete:
    """Experiment tenants with physical_delete policy permanently remove data."""

    @pytest.fixture
    async def exp_tenant(self, async_client):
        return await _create_tenant(async_client, "experiment")

    @pytest.mark.asyncio
    async def test_physical_delete_returns_counts(self, async_client, exp_tenant):
        """DELETE returns PhysicalDeleteResponse with deletion counts."""
        art = await _create_artifact(async_client, exp_tenant["id"], title="PhysDel")
        headers = {"X-Tenant-ID": str(exp_tenant["id"])}

        resp = await async_client.delete(f"/artifacts/{art['id']}", headers=headers)
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["deleted_id"] == art["id"]
        assert "deleted" in body
        assert body["deleted"]["artifacts"] >= 1

    @pytest.mark.asyncio
    async def test_physical_delete_truly_gone(self, async_client, exp_tenant):
        """After physical delete, artifact is gone even with include_deleted=true."""
        art = await _create_artifact(async_client, exp_tenant["id"], title="TrulyGone")
        headers = {"X-Tenant-ID": str(exp_tenant["id"])}

        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)

        # Should be 404 even with include_deleted
        resp = await async_client.get(
            f"/artifacts/{art['id']}", headers=headers, params={"include_deleted": "true"}
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_physical_delete_cascade(self, async_client, exp_tenant):
        """Physical cascade delete removes entire tree."""
        headers = {"X-Tenant-ID": str(exp_tenant["id"])}

        parent = await _create_artifact(async_client, exp_tenant["id"], title="PhysParent")
        child = await _create_artifact(async_client, exp_tenant["id"], title="PhysChild", parent_id=parent["id"])

        resp = await async_client.delete(
            f"/artifacts/{parent['id']}", headers=headers, params={"cascade": "true"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"]["artifacts"] == 2

        # Both gone
        for art_id in [parent["id"], child["id"]]:
            get_resp = await async_client.get(
                f"/artifacts/{art_id}", headers=headers, params={"include_deleted": "true"}
            )
            assert get_resp.status_code == 404


# =============================================================================
# Children Exclusion
# =============================================================================


@pytest.mark.integration
class TestChildrenExclusion:
    """GET /artifacts/{id}/children excludes soft-deleted children."""

    @pytest.fixture
    async def env_tenant(self, async_client):
        return await _create_tenant(async_client, "environment")

    @pytest.mark.asyncio
    async def test_soft_deleted_child_excluded_from_children_list(self, async_client, env_tenant):
        """Soft-deleted child does not appear in parent's children endpoint."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}

        parent = await _create_artifact(async_client, env_tenant["id"], title="ChParent")
        child1 = await _create_artifact(async_client, env_tenant["id"], title="ChKeep", parent_id=parent["id"])
        child2 = await _create_artifact(async_client, env_tenant["id"], title="ChDelete", parent_id=parent["id"])

        # Soft-delete child2
        await async_client.delete(f"/artifacts/{child2['id']}", headers=headers)

        # Get children of parent
        resp = await async_client.get(f"/artifacts/{parent['id']}/children", headers=headers)
        assert resp.status_code == 200
        child_ids = [c["id"] for c in resp.json()]
        assert child1["id"] in child_ids
        assert child2["id"] not in child_ids


# =============================================================================
# Provenance Preservation
# =============================================================================


@pytest.mark.integration
class TestProvenancePreservation:
    """Provenance events survive soft-delete."""

    @pytest.fixture
    async def env_tenant(self, async_client):
        return await _create_tenant(async_client, "environment")

    @pytest.mark.asyncio
    async def test_provenance_survives_soft_delete(self, async_client, env_tenant):
        """After soft-delete, provenance events for the artifact are still queryable."""
        headers = {"X-Tenant-ID": str(env_tenant["id"])}
        art = await _create_artifact(async_client, env_tenant["id"], title="ProvSurvive")

        # There should be a create provenance event
        prov_resp = await async_client.get(
            f"/provenance/artifact/{art['id']}", headers=headers
        )
        assert prov_resp.status_code == 200
        events_before = prov_resp.json()
        assert len(events_before) > 0

        # Soft-delete
        await async_client.delete(f"/artifacts/{art['id']}", headers=headers)

        # Provenance events should still be accessible
        prov_resp2 = await async_client.get(
            f"/provenance/artifact/{art['id']}", headers=headers
        )
        assert prov_resp2.status_code == 200
        events_after = prov_resp2.json()
        # Should have at least the create + soft_delete events
        assert len(events_after) >= len(events_before)


# =============================================================================
# Stress Tests — Cascade Delete of ~200 Artifact Tree
# =============================================================================


@pytest.mark.integration
class TestCascadeSoftDeleteStress:
    """Stress test: cascade soft-delete of a ~201 artifact tree (1 project → 10 files → 19 chunks)."""

    @pytest.fixture
    async def env_tenant(self, async_client):
        return await _create_tenant(async_client, "environment")

    @pytest.mark.asyncio
    async def test_cascade_soft_delete_200_artifact_tree(self, async_client, env_tenant):
        """Create 201-artifact tree, cascade soft-delete from root, verify all gone."""
        import time

        headers = {"X-Tenant-ID": str(env_tenant["id"])}
        tid = env_tenant["id"]

        # Level 1: Project root
        root = await _create_artifact(async_client, tid, title="Stress Root", artifact_type="document")
        root_id = root["id"]
        all_ids = [root_id]

        # Level 2: 10 files
        file_ids = []
        for i in range(10):
            f = await _create_artifact(async_client, tid, title=f"File {i}", parent_id=root_id, artifact_type="document")
            file_ids.append(f["id"])
            all_ids.append(f["id"])

        # Level 3: 19 chunks per file = 190 chunks
        for fid in file_ids:
            for j in range(19):
                c = await _create_artifact(async_client, tid, title=f"Chunk {j}", parent_id=fid, artifact_type="chunk")
                all_ids.append(c["id"])

        total = len(all_ids)
        print(f"\n  Created {total} artifacts for stress test")
        assert total == 201, f"Expected 201 artifacts, got {total}"

        # Cascade soft-delete from root
        start = time.perf_counter()
        resp = await async_client.delete(
            f"/artifacts/{root_id}", headers=headers, params={"cascade": "true"}
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200, resp.text
        body = resp.json()
        print(f"  Cascade soft-delete of {total} artifacts completed in {elapsed_ms:.0f}ms")
        print(f"  cascade_count={body['cascade_count']}, deleted_ids={len(body['deleted_ids'])}")

        assert body["cascade_count"] == 200  # 201 total - 1 root
        assert len(body["deleted_ids"]) == 201

        # Spot-check: root, a file, and a chunk should all be 404
        for check_id in [root_id, file_ids[0], all_ids[-1]]:
            get_resp = await async_client.get(f"/artifacts/{check_id}", headers=headers)
            assert get_resp.status_code == 404, f"Artifact {check_id} should be 404"

        # Spot-check: include_deleted should return them
        get_resp = await async_client.get(
            f"/artifacts/{root_id}", headers=headers, params={"include_deleted": "true"}
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["deleted_at"] is not None

        # Performance: should complete in under 5 seconds for 201 artifacts
        assert elapsed_ms < 5000, f"Cascade soft-delete took {elapsed_ms:.0f}ms (>5s threshold)"


@pytest.mark.integration
class TestCascadePhysicalDeleteStress:
    """Stress test: cascade physical-delete of a ~201 artifact tree."""

    @pytest.fixture
    async def exp_tenant(self, async_client):
        return await _create_tenant(async_client, "experiment")

    @pytest.mark.asyncio
    async def test_cascade_physical_delete_200_artifact_tree(self, async_client, exp_tenant):
        """Create 201-artifact tree with relations, cascade physical-delete, verify completely gone."""
        import time

        headers = {"X-Tenant-ID": str(exp_tenant["id"])}
        tid = exp_tenant["id"]

        # Level 1: Project root
        root = await _create_artifact(async_client, tid, title="PhysStress Root", artifact_type="document")
        root_id = root["id"]
        all_ids = [root_id]

        # Level 2: 10 files
        file_ids = []
        for i in range(10):
            f = await _create_artifact(async_client, tid, title=f"PhysFile {i}", parent_id=root_id, artifact_type="document")
            file_ids.append(f["id"])
            all_ids.append(f["id"])

        # Level 3: 19 chunks per file = 190 chunks
        chunk_ids = []
        for fid in file_ids:
            for j in range(19):
                c = await _create_artifact(async_client, tid, title=f"PhysChunk {j}", parent_id=fid, artifact_type="chunk")
                chunk_ids.append(c["id"])
                all_ids.append(c["id"])

        # Add some cross-references between files to test relation deletion
        relations_created = 0
        for i in range(0, len(file_ids) - 1, 2):
            await _create_relation(async_client, tid, file_ids[i], file_ids[i + 1])
            relations_created += 1

        total = len(all_ids)
        print(f"\n  Created {total} artifacts + {relations_created} relations for physical stress test")
        assert total == 201

        # Cascade physical-delete from root
        start = time.perf_counter()
        resp = await async_client.delete(
            f"/artifacts/{root_id}", headers=headers, params={"cascade": "true"}
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert resp.status_code == 200, resp.text
        body = resp.json()
        counts = body["deleted"]
        print(f"  Physical delete completed in {elapsed_ms:.0f}ms")
        print(f"  Deleted: artifacts={counts['artifacts']}, relations={counts['relations']}, "
              f"provenance={counts['provenance_events']}, embeddings={counts['embeddings']}")

        assert counts["artifacts"] == 201
        assert counts["relations"] >= relations_created

        # Spot-check: truly gone (even with include_deleted)
        for check_id in [root_id, file_ids[0], chunk_ids[0], chunk_ids[-1]]:
            get_resp = await async_client.get(
                f"/artifacts/{check_id}", headers=headers, params={"include_deleted": "true"}
            )
            assert get_resp.status_code == 404, f"Artifact {check_id} should be truly gone"

        # Performance: should complete in under 10 seconds (physical delete is heavier)
        assert elapsed_ms < 10000, f"Physical cascade delete took {elapsed_ms:.0f}ms (>10s threshold)"
