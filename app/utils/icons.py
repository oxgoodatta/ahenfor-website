"""Developer-controlled icon mapping. Admins never choose icons."""

SERVICE_ICON_RULES = [
    (("road", "infrastructure", "drainage", "bridge"), "road"),
    (("civil", "structural", "steel", "concrete"), "beam"),
    (("renovat", "rehabilit", "repair", "maintenance"), "renovate"),
    (("management", "manage", "supervis"), "clipboard"),
    (("consult", "design", "survey", "advis"), "compass"),
    (("building", "construction", "residential", "commercial"), "building"),
    (("mechanical", "electrical", "plumbing", "mep"), "gear"),
]


def service_icon(name):
    lowered = (name or "").lower()
    for keywords, icon in SERVICE_ICON_RULES:
        if any(k in lowered for k in keywords):
            return icon
    return "hardhat"
