"""Editable site copy and the homepage hero.

The developer defines every editable key in REGISTRY. The admin can change
values but never add keys, so templates always know what exists.
"""
from dataclasses import dataclass

from flask import g
from sqlalchemy import func, select

from app.extensions import db
from app.models import HeroConfig, MediaAsset, Project, ProjectStatus, PublicationStatus, SiteSetting


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    kind: str = "text"  # text | textarea | lines | email | url | tel | int | choice | media
    default: str = ""
    help: str = ""
    max_length: int = 500
    choices: tuple = ()


DEFAULT_INTRO = (
    "Ahenfor Engineering and Construction Limited delivers building, civil engineering and "
    "infrastructure projects, managing work from planning and design coordination through to "
    "construction and handover."
)

GROUPS = {
    "company": "Company profile",
    "contact": "Contact details",
    "social": "Social media",
    "stats": "Company statistics",
}

REGISTRY = [
    SettingDef("company_tagline", "Short tagline", "company",
               default="Engineering and construction, delivered with care.", max_length=160),
    SettingDef("company_intro", "Company introduction", "company", "textarea", DEFAULT_INTRO,
               "Shown on the homepage and the About page.", 1500),
    SettingDef("company_history", "Company history", "company", "textarea", "",
               "Leave blank to hide the history section.", 6000),
    SettingDef("company_mission", "Mission", "company", "textarea", "", "", 800),
    SettingDef("company_vision", "Vision", "company", "textarea", "", "", 800),
    SettingDef("company_values", "Core values", "company", "lines", "",
               'One value per line. Optionally "Safety: We plan every task around..."', 3000),
    SettingDef("about_image", "About section image", "company", "media"),
    SettingDef("footer_description", "Footer description", "company", "textarea",
               "Building, civil engineering and infrastructure delivery.", "", 300),

    SettingDef("contact_phone", "Phone number", "contact", "tel", max_length=40),
    SettingDef("contact_email", "Business email", "contact", "email", max_length=255),
    SettingDef("contact_address", "Office address", "contact", "textarea", max_length=400),
    SettingDef("contact_hours", "Office hours", "contact", max_length=120,
               help="For example: Mon-Fri, 8:00 to 17:00"),
    SettingDef("contact_whatsapp", "WhatsApp number", "contact", "tel", max_length=20,
               help="Digits in international format, e.g. 233241234567. Leave blank to hide."),
    SettingDef("contact_map_url", "Map / directions link", "contact", "url", max_length=500,
               help="A Google Maps share link for the office."),
    SettingDef("inquiry_notify_email", "Send new inquiries to", "contact", "email", max_length=255,
               help="Private. Not shown on the website."),

    SettingDef("social_linkedin", "LinkedIn", "social", "url"),
    SettingDef("social_facebook", "Facebook", "social", "url"),
    SettingDef("social_instagram", "Instagram", "social", "url"),
    SettingDef("social_x", "X (Twitter)", "social", "url"),
    SettingDef("social_youtube", "YouTube", "social", "url"),

    SettingDef("stat_years", "Years of experience", "stats", "int",
               help="Leave blank to hide. Only enter figures the company can verify."),
    SettingDef("stat_projects", "Projects completed", "stats", "int"),
    SettingDef("stat_projects_source", "Projects completed figure", "stats", "choice", "manual",
               "“Count published projects” counts each published project marked Completed once.",
               choices=(("manual", "Use the number entered above"),
                        ("derived", "Count published completed projects"))),
    SettingDef("stat_clients", "Clients served", "stats", "int"),
    SettingDef("stat_awards", "Awards and recognitions", "stats", "int"),
]

BY_KEY = {d.key: d for d in REGISTRY}
MEDIA_SETTING_KEYS = [d.key for d in REGISTRY if d.kind == "media"]
SOCIAL_KEYS = [d for d in REGISTRY if d.group == "social"]


class SiteContext:
    """Attribute access to settings with defaults: ``site.contact_phone``."""

    def __init__(self, values):
        self._values = values

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        definition = BY_KEY.get(key)
        if definition is None:
            raise AttributeError(f"Unknown site setting {key!r}")
        value = self._values.get(key)
        return value if value not in (None, "") else definition.default

    def is_custom(self, key):
        return self._values.get(key) not in (None, "")

    def lines(self, key):
        """Split a 'lines' setting into (title, description) pairs."""
        items = []
        for raw in (getattr(self, key) or "").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            title, sep, desc = raw.partition(":")
            items.append((title.strip(), desc.strip()) if sep else (raw, ""))
        return items

    def media(self, key):
        value = self._values.get(key)
        if not value:
            return None
        try:
            asset = db.session.get(MediaAsset, int(value))
        except (TypeError, ValueError):
            return None
        return asset if asset and not asset.is_private else None

    @property
    def whatsapp_url(self):
        digits = "".join(ch for ch in (self.contact_whatsapp or "") if ch.isdigit())
        return f"https://wa.me/{digits}" if digits else None

    @property
    def social_links(self):
        return [(d.label, getattr(self, d.key)) for d in SOCIAL_KEYS if getattr(self, d.key)]


def load_values():
    return {s.key: s.value for s in db.session.scalars(select(SiteSetting))}


def site():
    """Request-cached SiteContext."""
    if "site_context" not in g:
        g.site_context = SiteContext(load_values())
    return g.site_context


def save(values):
    """Persist a {key: value} mapping. Unknown keys are rejected."""
    for key, value in values.items():
        if key not in BY_KEY:
            raise KeyError(key)
        value = "" if value is None else str(value).strip()
        row = db.session.get(SiteSetting, key)
        if row is None:
            db.session.add(SiteSetting(key=key, value=value))
        else:
            row.value = value
    g.pop("site_context", None)


def public_stats():
    """Only statistics the company has entered (or the documented derived count)."""
    ctx = site()
    stats = []

    def add(value, label):
        if value not in (None, ""):
            stats.append({"value": int(value), "label": label})

    add(ctx.stat_years, "Years of experience")
    if ctx.stat_projects_source == "derived":
        count = db.session.scalar(
            select(func.count(Project.id)).where(
                Project.publication_status == PublicationStatus.PUBLISHED,
                Project.status == ProjectStatus.COMPLETED,
            )
        )
        if count:
            stats.append({"value": count, "label": "Projects completed"})
    else:
        add(ctx.stat_projects, "Projects completed")
    add(ctx.stat_clients, "Clients served")
    add(ctx.stat_awards, "Awards and recognitions")
    return stats


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------

HERO_TARGETS = {
    "projects": ("Projects", "public.projects"),
    "quote": ("Request a Quote", "public.request_quote"),
    "contact": ("Contact", "public.contact"),
    "services": ("Services", "public.services"),
    "about": ("About", "public.about"),
    "news": ("News and Events", "public.news_events"),
}

HERO_DEFAULTS = {
    "media_type": "image",
    "eyebrow": "Engineering and Construction",
    "headline": "Building structures that serve communities for generations.",
    "subheadline": (
        "From foundations to handover, Ahenfor plans, engineers and builds commercial, "
        "institutional and infrastructure projects with discipline and care."
    ),
    "primary_label": "Explore Projects",
    "primary_target": "projects",
    "secondary_label": "Request a Quote",
    "secondary_target": "quote",
}


def get_hero(state):
    hero = db.session.scalar(select(HeroConfig).where(HeroConfig.state == state))
    if hero is None:
        hero = HeroConfig(state=state, **HERO_DEFAULTS)
        db.session.add(hero)
        db.session.flush()
    return hero


def publish_hero(user=None):
    draft = get_hero("draft")
    published = get_hero("published")
    for field in HeroConfig.COPY_FIELDS:
        setattr(published, field, getattr(draft, field))
    published.updated_by_id = getattr(user, "id", None)
    db.session.commit()
    return published


def hero_has_unpublished_changes():
    draft, published = get_hero("draft"), get_hero("published")
    return any(getattr(draft, f) != getattr(published, f) for f in HeroConfig.COPY_FIELDS)
