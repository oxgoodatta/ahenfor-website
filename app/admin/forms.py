"""Admin forms. Media slots are a FileField (new upload) plus a HiddenField
(selected library item id); see media_service.resolve_media_field."""
from datetime import date

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, MultipleFileField
from wtforms import (
    BooleanField,
    DateField,
    DateTimeLocalField,
    EmailField,
    HiddenField,
    IntegerField,
    PasswordField,
    RadioField,
    SelectField,
    StringField,
    TelField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, ValidationError

from app.models import (
    PROJECT_CATEGORIES,
    InquiryStatus,
    PhaseStatus,
    PostKind,
    ProjectStatus,
    PublicationStatus,
)
from app.models.user import MIN_PASSWORD_LENGTH
from app.services.settings_service import HERO_TARGETS
from app.utils.helpers import SLUG_RE
from app.utils.validators import HttpUrl

VISIBILITY_CHOICES = PublicationStatus.choices(exclude=(PublicationStatus.ARCHIVED,))
SLUG_HELP = "Lower-case letters, numbers and hyphens. Leave blank to create it from the title."


def slug_field(label="URL slug"):
    return StringField(label, [Optional(), Length(max=200),
                               Regexp(SLUG_RE, message="Use lower-case letters, numbers and hyphens only.")],
                       description=SLUG_HELP)


def visibility_field():
    return SelectField("Visibility", choices=VISIBILITY_CHOICES, default=PublicationStatus.DRAFT.value,
                       description="Drafts are never shown on the public website.")


class LoginForm(FlaskForm):
    email = EmailField("Email", [DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField("Password", [DataRequired(), Length(max=200)])


class ConfirmForm(FlaskForm):
    """CSRF-only form for POST action buttons."""


class ProjectForm(FlaskForm):
    name = StringField("Project name", [DataRequired(), Length(max=200)])
    slug = slug_field()
    reference_code = StringField("Reference code", [Optional(), Length(max=50)],
                                 description="Optional internal reference, e.g. AEC-2026-014.")
    location = StringField("Location", [DataRequired(), Length(max=200)], description="Town and region.")
    category = SelectField("Category", choices=[(c, c) for c in PROJECT_CATEGORIES])
    short_description = TextAreaField("Short description", [DataRequired(), Length(max=300)],
                                      description="One or two sentences for project cards (max 300 characters).")
    description = TextAreaField("Full description", [Optional(), Length(max=20000)],
                                description="Plain text. Leave a blank line between paragraphs.")

    cover_image_file = FileField("Cover image")
    cover_image_id = HiddenField()
    cover_image_alt = StringField("Cover image description (alt text)", [Optional(), Length(max=255)],
                                  description="Describe the photo for visitors using screen readers.")
    cover_video_file = FileField("Cover video (optional)")
    cover_video_id = HiddenField()

    status = SelectField("Project status", choices=ProjectStatus.choices())
    progress_percent = IntegerField("Progress shown publicly (%)", [Optional(), NumberRange(0, 100)],
                                    description="Leave blank to hide. Enter only a figure confirmed by the site team.")
    start_date = DateField("Start date", [Optional()])
    estimated_completion_date = DateField("Estimated completion", [Optional()])
    actual_completion_date = DateField("Actual completion", [Optional()])

    client_name = StringField("Client name", [Optional(), Length(max=200)])
    show_client = BooleanField("The client has approved showing their name publicly")
    project_value = StringField("Project value", [Optional(), Length(max=100)], description="e.g. GH₵ 4.2 million")
    show_value = BooleanField("Show the project value publicly")

    is_featured = BooleanField("Feature this project on the homepage")
    featured_order = IntegerField("Featured order", [Optional(), NumberRange(0, 999)], default=0,
                                  description="Lower numbers appear first.")
    publication_status = visibility_field()

    def validate_estimated_completion_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError("Estimated completion cannot be before the start date.")

    def validate_actual_completion_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError("Actual completion cannot be before the start date.")
        if field.data and field.data > date.today():
            raise ValidationError("Actual completion cannot be in the future.")


class PhaseForm(FlaskForm):
    title = StringField("Phase title", [DataRequired(), Length(max=160)])
    description = TextAreaField("Description", [Optional(), Length(max=5000)])
    status = SelectField("Phase status", choices=PhaseStatus.choices())
    start_date = DateField("Start date", [Optional()])
    completed_date = DateField("Completion date", [Optional()])

    def validate_completed_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError("Completion cannot be before the start date.")


class ProgressUpdateForm(FlaskForm):
    phase_id = SelectField("Construction phase", coerce=int, validators=[DataRequired()])
    title = StringField("Update summary", [DataRequired(), Length(max=200)],
                        description="A short headline, e.g. “First-floor slab cast”.")
    update_date = DateField("Date of work", [DataRequired()], default=date.today)
    body = TextAreaField("Details (optional)", [Optional(), Length(max=10000)])
    photos = MultipleFileField("Add photos")
    video_file = FileField("Video (optional)")
    video_id = HiddenField()
    publication_status = visibility_field()

    def validate_update_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("The date of work cannot be in the future.")


class HeroForm(FlaskForm):
    media_type = RadioField("Background type", choices=[("image", "Image"), ("video", "Video")], default="image")
    image_file = FileField("Background image")
    image_id = HiddenField()
    video_file = FileField("Background video")
    video_id = HiddenField()
    poster_file = FileField("Video poster image")
    poster_id = HiddenField()
    alt_text = StringField("Image description (alt text)", [Optional(), Length(max=255)])
    eyebrow = StringField("Small label above the headline", [Optional(), Length(max=80)])
    headline = StringField("Headline", [DataRequired(), Length(max=160)])
    subheadline = TextAreaField("Supporting text", [Optional(), Length(max=400)])
    primary_label = StringField("Main button text", [DataRequired(), Length(max=40)])
    primary_target = SelectField("Main button goes to", choices=[(k, v[0]) for k, v in HERO_TARGETS.items()])
    secondary_label = StringField("Second button text", [Optional(), Length(max=40)],
                                  description="Leave blank to hide the second button.")
    secondary_target = SelectField("Second button goes to", choices=[(k, v[0]) for k, v in HERO_TARGETS.items()])


class PostForm(FlaskForm):
    title = StringField("Title", [DataRequired(), Length(max=200)])
    slug = slug_field()
    kind = SelectField("Type", choices=PostKind.choices())
    summary = TextAreaField("Summary", [DataRequired(), Length(max=400)],
                            description="Shown on listing cards (max 400 characters).")
    body = TextAreaField("Full description", [Optional(), Length(max=20000)])
    cover_image_file = FileField("Cover image")
    cover_image_id = HiddenField()
    video_file = FileField("Video (optional)")
    video_id = HiddenField()
    starts_at = DateTimeLocalField("Event starts", [Optional()], format="%Y-%m-%dT%H:%M",
                                   description="Required for events. Times are Ghana time (GMT).")
    ends_at = DateTimeLocalField("Event ends", [Optional()], format="%Y-%m-%dT%H:%M")
    venue = StringField("Venue", [Optional(), Length(max=200)])
    registration_url = StringField("Registration link", [Optional(), Length(max=500), HttpUrl()])
    published_at = DateTimeLocalField("Publication date", [Optional()], format="%Y-%m-%dT%H:%M",
                                      description="Leave blank to publish immediately. A future date schedules it.")
    publication_status = visibility_field()

    def validate(self, extra_validators=None):
        # Checked here because Optional() stops the field's own validator chain when empty.
        valid = super().validate(extra_validators)
        if self.kind.data == PostKind.EVENT.value and not self.starts_at.data and not self.starts_at.errors:
            self.starts_at.errors = list(self.starts_at.errors) + ["Events need a start date and time."]
            valid = False
        return valid

    def validate_ends_at(self, field):
        if field.data and not self.starts_at.data:
            raise ValidationError("Set a start date before an end date.")
        if field.data and self.starts_at.data and field.data < self.starts_at.data:
            raise ValidationError("The event cannot end before it starts.")


class ServiceForm(FlaskForm):
    name = StringField("Service name", [DataRequired(), Length(max=150)])
    short_description = TextAreaField("Short description", [DataRequired(), Length(max=300)])
    description = TextAreaField("Full description", [Optional(), Length(max=10000)])
    image_file = FileField("Supporting image (optional)")
    image_id = HiddenField()
    position = IntegerField("Display order", [Optional(), NumberRange(0, 999)], default=0)
    publication_status = visibility_field()


class AwardForm(FlaskForm):
    title = StringField("Award or certification", [DataRequired(), Length(max=200)])
    issuer = StringField("Issuing organisation", [DataRequired(), Length(max=200)])
    year = IntegerField("Year", [Optional(), NumberRange(1950, 2100)])
    description = TextAreaField("Description", [Optional(), Length(max=4000)])
    image_file = FileField("Image (optional)")
    image_id = HiddenField()
    document_file = FileField("Supporting document (PDF, optional)")
    document_id = HiddenField()
    position = IntegerField("Display order", [Optional(), NumberRange(0, 999)], default=0)
    publication_status = visibility_field()


class TestimonialForm(FlaskForm):
    client_name = StringField("Client name", [DataRequired(), Length(max=150)])
    client_role = StringField("Role / title", [Optional(), Length(max=150)])
    organization = StringField("Organisation", [Optional(), Length(max=200)])
    quote = TextAreaField("Testimonial", [DataRequired(), Length(max=2000)])
    portrait_file = FileField("Portrait or company logo (optional)")
    portrait_id = HiddenField()
    project_id = SelectField("Related project (optional)", coerce=int, default=0)
    client_approved = BooleanField("The client has approved this exact wording for publication")
    position = IntegerField("Display order", [Optional(), NumberRange(0, 999)], default=0)
    publication_status = visibility_field()

    def validate_client_approved(self, field):
        if self.publication_status.data == PublicationStatus.PUBLISHED.value and not field.data:
            raise ValidationError("Testimonials can only be published after the client has approved them.")


class InquiryForm(FlaskForm):
    status = SelectField("Status", choices=InquiryStatus.choices())
    internal_notes = TextAreaField("Internal notes", [Optional(), Length(max=10000)],
                                   description="Private. Never shown to the client.")


class MediaEditForm(FlaskForm):
    alt_text = StringField("Description (alt text)", [Optional(), Length(max=255)])
    caption = StringField("Default caption", [Optional(), Length(max=300)])


class PasswordChangeForm(FlaskForm):
    current_password = PasswordField("Current password", [DataRequired()])
    new_password = PasswordField("New password", [DataRequired(), Length(min=MIN_PASSWORD_LENGTH, max=200)])
    confirm_password = PasswordField("Confirm new password",
                                     [DataRequired(), EqualTo("new_password", message="Passwords do not match.")])


def build_settings_form(definitions, values):
    """Create a form class for a group of SettingDefs."""

    class _SettingsForm(FlaskForm):
        pass

    for d in definitions:
        validators = [Optional(), Length(max=d.max_length)]
        kwargs = {"description": d.help, "default": values.get(d.key, "") or d.default}
        if d.kind == "media":
            setattr(_SettingsForm, d.key + "_file", FileField(d.label))
            setattr(_SettingsForm, d.key + "_id", HiddenField(default=values.get(d.key, "")))
            continue
        if d.kind in ("textarea", "lines"):
            field = TextAreaField(d.label, validators, **kwargs)
        elif d.kind == "email":
            field = EmailField(d.label, validators + [Email(check_deliverability=False)], **kwargs)
        elif d.kind == "url":
            field = StringField(d.label, validators + [HttpUrl()], **kwargs)
        elif d.kind == "tel":
            field = TelField(d.label, validators, **kwargs)
        elif d.kind == "int":
            field = IntegerField(d.label, [Optional(), NumberRange(0, 100000)], description=d.help,
                                 default=int(values[d.key]) if values.get(d.key, "").isdigit() else None)
        elif d.kind == "choice":
            field = SelectField(d.label, choices=list(d.choices), **kwargs)
        else:
            field = StringField(d.label, validators, **kwargs)
        setattr(_SettingsForm, d.key, field)
    return _SettingsForm
