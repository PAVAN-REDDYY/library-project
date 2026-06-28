from rest_framework import generics, viewsets

from .models import BookRental
from .serializers import BookRentalSerializer


# One ViewSet gives the whole CRUD API. The router in urls.py expands it into
# the /api/book-rentals/ and /api/book-rentals/<id>/ endpoints.
class BookRentalViewSet(viewsets.ModelViewSet):
    queryset = BookRental.objects.all()
    serializer_class = BookRentalSerializer


# The brief also asks for DRF's generic views, so the same model is exposed a
# second time under /api/generic/book-rentals/.
class BookRentalListCreateAPIView(generics.ListCreateAPIView):
    queryset = BookRental.objects.all()
    serializer_class = BookRentalSerializer


class BookRentalDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = BookRental.objects.all()
    serializer_class = BookRentalSerializer
