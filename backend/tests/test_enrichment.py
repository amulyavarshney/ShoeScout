from sqlalchemy import select

from app.db import EnrichedAttributes, EnrichmentJob, ProductImage
from app.enrichment.worker import enqueue_changed, process_job, validate_attributes
from app.seed.demo_catalog import content_hash


def test_validate_disagreement_flags_review():
    attrs, review, evidence = validate_attributes({"primary_color": "red", "secondary_colors": [], "category": "casual", "style": "sneaker", "tags": []},
                                                  "Burgundy suede low-top", None)
    assert review == "needs_review" and attrs["primary_color"] == "burgundy" and "red" in attrs["secondary_colors"]


def test_validate_unknown_color_needs_review():
    attrs, review, _ = validate_attributes({"primary_color": "unknown", "secondary_colors": [], "category": "unknown", "style": "unknown", "tags": []}, "", None)
    assert attrs["primary_color"] is None and review == "needs_review"


async def test_enqueue_only_changed_and_broken_image_fails(db):
    res = await enqueue_changed(db)
    # fixture rows were produced by 'fixture-v1'; mock vision version differs -> all groups queued once
    assert res["queued"] > 0
    again = await enqueue_changed(db)
    assert again["queued"] == 0  # idempotent
    jobs = (await db.execute(select(EnrichmentJob).where(EnrichmentJob.status == "queued"))).scalars().all()
    broken = next(j for j in jobs if j.image_group_id == "MODEL-130-WHE")
    good = next(j for j in jobs if j.image_group_id == "MODEL-101-RED")
    await process_job(db, broken)
    await process_job(db, good)
    assert broken.status in ("failed", "dead") and broken.error_code
    assert good.status == "done"
    a = (await db.execute(select(EnrichedAttributes).where(EnrichedAttributes.image_group_id == "MODEL-101-RED"))).scalar_one()
    assert a.primary_color == "red" and a.source == "fixture" and a.model_version == good.model_version


async def test_image_hash_change_requeues_only_that_group(db):
    img = (await db.execute(select(ProductImage).where(ProductImage.image_group_id == "MODEL-103-RED"))).scalar_one()
    img.content_hash = content_hash("changed")
    await db.commit()
    # mark everything else done with current version
    for j in (await db.execute(select(EnrichmentJob))).scalars():
        if j.status == "queued":
            j.status = "done"
    await db.commit()
    res = await enqueue_changed(db)
    assert res["queued"] == 1  # T19
