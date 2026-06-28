# Library Book Rental System

This Django project is used by library staff to keep track of book rentals. It
records who borrowed which book, the rental and return dates, the status of the
rental and any fine that is due. It is the fourth project in my Django CRUD
assessment.

It has both a template based website and a REST API working on the same data,
and the records are kept in a MySQL database.

## Tools I used

- Python 3
- Django
- Django REST Framework
- MySQL
- HTML, CSS and a little JavaScript

## What it does

Each rental stores the book title and author, the borrower's name and email, the
rental date and return date, a status (Borrowed, Returned, Overdue or Lost), and
a fine amount (which is 0.00 by default).

From the website you can:

- add a new rental
- view the list of all rentals
- open a rental to see its full details
- update a rental
- delete a rental (after confirming)

The REST API supports the same operations.

## Folder structure

```
library_book_rental/
├── manage.py
├── requirements.txt
├── core/               # settings and main urls
└── rentals/            # the app
    ├── models.py       # the BookRental table
    ├── forms.py        # BookRentalForm (used to add and update rentals)
    ├── views.py        # function based + class based views
    ├── serializers.py  # model to JSON for the API
    ├── api_views.py    # ViewSet + generic API views
    ├── urls.py
    └── templates/      # the HTML pages, all extending base.html
```

## How to run it

Make sure Python and MySQL are installed.

1. Open a terminal in this folder.

2. (Optional) set up a virtual environment:

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the packages:

   ```
   pip install -r requirements.txt
   ```

   If `mysqlclient` gives trouble while installing, run `pip install pymysql`
   instead.

4. Create the database inside MySQL:

   ```sql
   CREATE DATABASE library_rental_db CHARACTER SET utf8mb4;
   ```

   The database settings are in `core/settings.py` (user `root`, password
   `0000`). Update the password there if needed.

5. Create the tables and start the server:

   ```
   python manage.py migrate
   python manage.py runserver
   ```

6. Open http://127.0.0.1:8000/ and press Ctrl + C when you want to stop.

## Pages and their URLs

| Page | URL |
|------|-----|
| Home | `/` |
| All rentals | `/rentals/` |
| Rental details | `/rentals/<id>/` |
| Add rental | `/rentals/add/` |
| Update rental | `/rentals/<id>/update/` |
| Delete rental | `/rentals/<id>/delete/` |

## API

ModelViewSet with a router:

- `GET` / `POST` → `/api/book-rentals/`
- `GET` / `PUT` / `PATCH` / `DELETE` → `/api/book-rentals/<id>/`

Generic API views (the assessment asked for these as well):

- `/api/generic/book-rentals/`
- `/api/generic/book-rentals/<id>/`

## A few notes

- The Home, list and detail pages are function based views, and adding, updating
  and deleting use class based views (CreateView, UpdateView, DeleteView).
- `BookRentalForm` is a ModelForm used on both the add and update pages.
- The fine amount defaults to 0.00 and can be set when a book is late or lost.
