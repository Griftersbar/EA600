from wagtail import blocks
from wagtail.blocks import StreamBlockValidationError


ENQUIRY_FIELDS = {
    "business_name": "Business name",
    "contact_name": "Your name",
    "location": "Town or nearest route stop",
    "message": "What would you like to know?",
}


class EnquiryQuestionBlock(blocks.StructBlock):
    label = blocks.CharBlock(max_length=120)
    help_text = blocks.CharBlock(required=False, max_length=240)
    required = blocks.BooleanBlock(default=False, required=False)

    class Meta:
        label_format = "{label}"


class StandardEnquiryFieldBlock(EnquiryQuestionBlock):
    field = blocks.ChoiceBlock(choices=list(ENQUIRY_FIELDS.items()), label="Save answer as")

    class Meta:
        label = "Standard enquiry field"


class ReplyEmailBlock(blocks.StructBlock):
    label = blocks.CharBlock(default="Email for replies", max_length=120)
    help_text = blocks.CharBlock(required=False, max_length=240)

    class Meta:
        label = "Reply email (required)"
        label_format = "{label}"


class DropdownQuestionBlock(EnquiryQuestionBlock):
    options = blocks.ListBlock(blocks.CharBlock(max_length=120), min_num=2, label="Choices")

    class Meta:
        label = "Dropdown"


class EnquiryFieldsBlock(blocks.StreamBlock):
    standard = StandardEnquiryFieldBlock()
    reply_email = ReplyEmailBlock()
    short_text = EnquiryQuestionBlock(label="Short text")
    long_text = EnquiryQuestionBlock(label="Long text")
    website = EnquiryQuestionBlock(label="Website URL")
    dropdown = DropdownQuestionBlock()

    class Meta:
        block_counts = {"reply_email": {"min_num": 1, "max_num": 1}}

    def clean(self, value):
        cleaned = super().clean(value)
        standard_fields = [block.value["field"] for block in cleaned if block.block_type == "standard"]
        if len(standard_fields) != len(set(standard_fields)):
            raise StreamBlockValidationError(non_block_errors=["Use each standard enquiry field once."])
        return cleaned


def default_enquiry_fields():
    standard = [
        ("standard", {"field": field, "label": label, "required": True})
        for field, label in ENQUIRY_FIELDS.items()
    ]
    standard.insert(2, ("reply_email", {"label": "Email for replies"}))
    return standard


class AdvertiserCardBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=100)
    description = blocks.TextBlock()

    class Meta:
        label_format = "{heading}"


class AdvertiserCardsBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=120)
    cards = blocks.ListBlock(AdvertiserCardBlock(), min_num=1)

    class Meta:
        label = "Information cards"
        label_format = "{heading}"


class AdvertiserNoteBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=120)
    description = blocks.TextBlock()

    class Meta:
        label = "Callout"
        label_format = "{heading}"


def default_advertiser_sections():
    return [
        ("cards", {"heading": "Who can advertise?", "cards": [
            {"heading": "Food and drink", "description": "Pubs, restaurants, cafés and tea rooms near a route stop."},
            {"heading": "Places to stay", "description": "Hotels, B&Bs and other visitor accommodation along the route."},
            {"heading": "Shops and makers", "description": "Independent shops, local producers and craft businesses."},
        ]}),
        ("cards", {"heading": "What your listing includes", "cards": [
            {"heading": "A place on the route", "description": "Your business appears beside a relevant stop while visitors plan their trip."},
            {"heading": "Direct links", "description": "Add a photo, directions and a link to your website or booking page."},
            {"heading": "Click reporting", "description": "See 30-day totals for website, booking and directions clicks."},
        ]}),
        ("note", {"heading": "What happens next?", "description": (
            "Enquire to discuss the best stop for your business. We review listing applications before payment. "
            "Once we approve your listing and confirm payment, it appears on the route."
        )}),
    ]
