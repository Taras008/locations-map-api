from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from rest_framework.utils.urls import remove_query_param, replace_query_param

LINK_FIELDS = ("next", "previous")


class DefaultPagination(PageNumberPagination):
    page_size = settings.PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = settings.MAX_PAGE_SIZE

    def dump_page(self, data: dict) -> dict:
        """
        Сторінка для кешу без next/previous: посилання абсолютні й містять host і всі
        параметри запиту, тож мають будуватися з кожного запиту окремо (load_page).
        """
        return {
            "data": {key: value for key, value in data.items() if key not in LINK_FIELDS},
            "number": self.page.number,
            "has_next": self.page.has_next(),
            "has_previous": self.page.has_previous(),
        }

    def load_page(self, request, cached: dict) -> dict:
        """Відповідь з dump_page() з посиланнями для поточного запиту — як у get_*_link()."""
        url = request.build_absolute_uri()
        number = cached["number"]
        next_link = previous_link = None
        if cached["has_next"]:
            next_link = replace_query_param(url, self.page_query_param, number + 1)
        if cached["has_previous"]:
            if number - 1 == 1:
                previous_link = remove_query_param(url, self.page_query_param)
            else:
                previous_link = replace_query_param(url, self.page_query_param, number - 1)
        data = cached["data"]
        return {"count": data["count"], "next": next_link, "previous": previous_link, **data}
