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
