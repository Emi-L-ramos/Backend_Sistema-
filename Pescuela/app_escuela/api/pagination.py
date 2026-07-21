from rest_framework.pagination import PageNumberPagination


class PaginacionOpcional(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_page_size(self, request):
        solicita_paginacion = (
            'page' in request.query_params
            or self.page_size_query_param
            in request.query_params
        )

        if not solicita_paginacion:
            return None

        return super().get_page_size(request)