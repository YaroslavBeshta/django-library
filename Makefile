start:
	docker compose up --build -d

stop:
	docker compose down

migrate:
	docker compose run web python manage.py makemigrations
	docker compose run web python manage.py migrate

createsuperuser:
	docker compose run web python manage.py createsuperuser