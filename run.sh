sudo docker build -t fastapi .

sudo docker run -p 8000:8000 --env-file .env fastapi