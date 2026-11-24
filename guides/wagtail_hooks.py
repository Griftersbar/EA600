from wagtail import hooks

from .choosers import photo_chooser, tour_chooser


@hooks.register("register_admin_viewset")
def register_guide_choosers():
    return [photo_chooser, tour_chooser]
