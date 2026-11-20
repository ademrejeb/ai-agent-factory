from app.errors import AppError

DRAFT = "draft"
CONFIGURED = "configured"
TESTED = "tested"
VALIDATED = "validated"
PUBLISHED = "published"
MONITORED = "monitored"
FAILED = "failed"
DEACTIVATED = "deactivated"

ALLOWED = {
    DRAFT: {CONFIGURED, FAILED, DEACTIVATED},
    CONFIGURED: {TESTED, FAILED, DEACTIVATED, DRAFT},
    TESTED: {VALIDATED, CONFIGURED, FAILED, DEACTIVATED},
    VALIDATED: {PUBLISHED, TESTED, FAILED, DEACTIVATED},
    PUBLISHED: {MONITORED, FAILED, DEACTIVATED},
    MONITORED: {PUBLISHED, FAILED, DEACTIVATED},
    FAILED: {DRAFT, CONFIGURED, DEACTIVATED},
    DEACTIVATED: {DRAFT},
}

EXECUTABLE_TEST = {CONFIGURED, TESTED, VALIDATED, PUBLISHED, MONITORED}
EXECUTABLE_GATEWAY = {PUBLISHED, MONITORED}


def transition(current: str, target: str) -> str:
    if current == target:
        return current
    allowed = ALLOWED.get(current, set())
    if target not in allowed:
        raise AppError(
            "invalid_lifecycle",
            f"Cannot transition agent from {current} to {target}.",
            409,
            {"from": current, "to": target},
        )
    return target
