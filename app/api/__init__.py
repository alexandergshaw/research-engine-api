"""API blueprint registration."""

from __future__ import annotations

from flask_smorest import Api


def register_blueprints(api: Api) -> None:
    from .v1.academic import blp as academic_blp
    from .v1.companies import blp as companies_blp
    from .v1.concepts import blp as concepts_blp
    from .v1.health import blp as health_blp
    from .v1.jobs import blp as jobs_blp
    from .v1.research import blp as research_blp
    from .v1.roles import blp as roles_blp
    from .v1.security import blp as security_blp
    from .v1.slides import blp as slides_blp

    for blp in (
        health_blp,
        research_blp,
        concepts_blp,
        security_blp,
        academic_blp,
        companies_blp,
        roles_blp,
        slides_blp,
        jobs_blp,
    ):
        api.register_blueprint(blp)

    # Document intent-specific data shapes that aren't tied to a single endpoint
    # (they're served via the generic /v1/research) so they appear in /openapi.json.
    from app.schemas import CompanyNewsDataSchema, FeedPollDataSchema

    api.spec.components.schema("CompanyNewsData", schema=CompanyNewsDataSchema)
    api.spec.components.schema("FeedPollData", schema=FeedPollDataSchema)
