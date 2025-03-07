from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Author, Book, Member, Loan
from .serializers import (
    AuthorSerializer,
    BookSerializer,
    MemberSerializer,
    LoanSerializer,
    MemberWithLoanCountSerializer,
)
from rest_framework.decorators import action
from django.utils import timezone
from .tasks import send_loan_notification
from django.db.models import Count


class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.select_related("author").all()
    serializer_class = BookSerializer

    @action(detail=True, methods=["post"])
    def loan(self, request, pk=None):
        book = self.get_object()
        if book.available_copies < 1:
            return Response(
                {"error": "No available copies."}, status=status.HTTP_400_BAD_REQUEST
            )
        member_id = request.data.get("member_id")
        try:
            member = Member.objects.get(id=member_id)
        except Member.DoesNotExist:
            return Response(
                {"error": "Member does not exist."}, status=status.HTTP_400_BAD_REQUEST
            )
        loan = Loan.objects.create(book=book, member=member)
        book.available_copies -= 1
        book.save()
        send_loan_notification.delay(loan.id)
        return Response(
            {"status": "Book loaned successfully."}, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def return_book(self, request, pk=None):
        book = self.get_object()
        member_id = request.data.get("member_id")
        try:
            loan = Loan.objects.get(book=book, member__id=member_id, is_returned=False)
        except Loan.DoesNotExist:
            return Response(
                {"error": "Active loan does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        loan.is_returned = True
        loan.return_date = timezone.now().date()
        loan.save()
        book.available_copies += 1
        book.save()
        return Response(
            {"status": "Book returned successfully."}, status=status.HTTP_200_OK
        )


class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer


class LoanViewSet(viewsets.ModelViewSet):
    queryset = Loan.objects.all()
    serializer_class = LoanSerializer

    @action(detail=True, methods=["post"])
    def extend_due_date(self, request, pk=None):
        loan = self.get_object()
        additional_days = request.data.get("additional_days")
        if loan.due_date <= timezone.now():
            return Response(
                {"error": "Loan is overdue"}, status=status.HTTP_400_BAD_REQUEST
            )
        if additional_days < 0:
            return Response(
                {"error": "Additional dats has to be a positive integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            loan.due_date = loan.due_date + timedelta(days=additional_days)
        except:
            return Response({"error": "Failed to update"}, status=status.HTTP_200_OK)
        loan.save()
        return Response(
            {"status": "Loan extended successfully."}, status=status.HTTP_200_OK
        )


@api_view(["GET"])
def members_with_most_loans(request):
    top_members = Member.objects.annotate(num_loans=Count("loans")).order_by(
        "-num_loans"
    )[:5]
    if top_members:
        serializer = MemberWithLoanCountSerializer(top_members)
        return Response(serializer.data)
    return Response({"error": "No members found."}, status=404)
