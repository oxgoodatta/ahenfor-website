from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import EmailField, SelectField, StringField, TelField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from app.utils.validators import Digits

BUDGET_CHOICES = [
    ("", "Prefer not to say"),
    ("Under GH₵ 500,000", "Under GH₵ 500,000"),
    ("GH₵ 500,000 – 2 million", "GH₵ 500,000 – 2 million"),
    ("GH₵ 2 – 10 million", "GH₵ 2 – 10 million"),
    ("Over GH₵ 10 million", "Over GH₵ 10 million"),
]

TIMELINE_CHOICES = [
    ("", "Select a timeline"),
    ("As soon as possible", "As soon as possible"),
    ("Within 3 months", "Within 3 months"),
    ("3 – 6 months", "3 – 6 months"),
    ("6 – 12 months", "6 – 12 months"),
    ("More than 12 months", "More than 12 months"),
    ("Not decided", "Not decided yet"),
]


class _SpamProtected(FlaskForm):
    # Honeypot: hidden from people, often filled by bots.
    company_website = StringField("Leave this field empty", validators=[Optional(), Length(max=200)])

    @property
    def is_spam(self):
        return bool((self.company_website.data or "").strip())


class ContactForm(_SpamProtected):
    full_name = StringField("Full name", [DataRequired(), Length(max=150)])
    email = EmailField("Email", [DataRequired(), Email(check_deliverability=False), Length(max=255)])
    phone = TelField("Phone number", [Optional(), Length(max=40), Digits()])
    subject = StringField("Subject", [DataRequired(), Length(max=200)])
    message = TextAreaField("Message", [DataRequired(), Length(min=10, max=5000)])


class QuoteForm(_SpamProtected):
    full_name = StringField("Full name", [DataRequired(), Length(max=150)])
    email = EmailField("Email", [DataRequired(), Email(check_deliverability=False), Length(max=255)])
    phone = TelField("Telephone number", [DataRequired(), Length(max=40), Digits()])
    organization = StringField("Organisation", [Optional(), Length(max=200)])
    project_location = StringField("Project location", [DataRequired(), Length(max=200)])
    service = SelectField("Service required", validators=[DataRequired(message="Select a service.")])
    message = TextAreaField("Project description", [DataRequired(), Length(min=20, max=8000)],
                            description="Scope, size, current stage (land, drawings, permits) and anything else we should know.")
    budget_range = SelectField("Budget range", choices=BUDGET_CHOICES, validators=[Optional()])
    timeline = SelectField("Expected timeline", choices=TIMELINE_CHOICES,
                           validators=[DataRequired(message="Select a timeline.")])
    attachment = FileField("Project brief or drawings",
                           description="Optional. PDF, DOCX, DWG, JPG or PNG, up to the size limit.")
